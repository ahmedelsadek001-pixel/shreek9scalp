"""Build and verify complete source ZIPs against an independently pinned Git commit."""
from __future__ import annotations

import argparse
import base64
import binascii
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import zipfile
import zlib


MANIFEST_NAME = "shreek-source-manifest.json"
MAX_FILES = 10000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_BYTES = MAX_TOTAL_BYTES + 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_COMMIT_BYTES = 64 * 1024
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_RESERVED = frozenset({"con", "prn", "aux", "nul"} | {
    prefix + str(number) for prefix in ("com", "lpt") for number in range(1, 10)
})


def _result(reason: str = "source archive unavailable or invalid") -> dict:
    return {
        "schema": "shreek.source-archive-check.v1", "state": "blocked", "reason": reason,
        "commit_sha": None, "tree_sha": None, "file_count": 0,
        "archive_sha256": None, "manifest_sha256": None,
        "source_commit_verified": False, "source_tree_verified": False,
        "signature_verified": False, "runtime_source_verified": False,
        "order_transport_enabled": False, "release_authorized": False, "live_authorized": False,
    }


def _identity(value: object, pattern: re.Pattern = _SHA) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _object_sha(kind: str, data: bytes) -> str:
    return sha1((kind + " " + str(len(data))).encode("ascii") + b"\0" + data).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest field")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite manifest value")


def _safe_path(path: object) -> bool:
    if type(path) is not str or not path or len(path.encode("utf-8")) > 4096:
        return False
    if any(ch in path for ch in '\\:<>"|?*') or any(ord(ch) < 32 or ord(ch) == 127 for ch in path):
        return False
    for part in path.split("/"):
        if (part in ("", ".", "..") or part.casefold() == ".git"
                or part.endswith((".", " "))
                or part.split(".")[0].casefold() in _WINDOWS_RESERVED):
            return False
    return path.casefold() != MANIFEST_NAME.casefold()


def _tree_sha(files: list[dict]) -> str:
    root = {}
    spelling = {}
    for entry in files:
        parts = entry["path"].split("/")
        current = root
        for index, part in enumerate(parts):
            prefix = "/".join(parts[:index + 1])
            folded = prefix.casefold()
            if folded in spelling and spelling[folded] != prefix:
                raise ValueError("nonportable case collision")
            spelling[folded] = prefix
            if index == len(parts) - 1:
                if part in current:
                    raise ValueError("duplicate path or file/directory collision")
                current[part] = (entry["mode"], entry["git_blob_sha"])
            else:
                node = current.setdefault(part, {})
                if not isinstance(node, dict):
                    raise ValueError("file/directory collision")
                current = node

    def tree(node: dict) -> str:
        # Git compares directory names with a trailing slash when ordering a
        # tree, so a directory 'a' sorts after a file named 'a.txt'.
        data = bytearray()
        for name, value in sorted(node.items(), key=lambda item: (
                item[0].encode("utf-8") + (b"/" if isinstance(item[1], dict) else b""))):
            mode, digest = ("40000", tree(value)) if isinstance(value, dict) else value
            data.extend(mode.encode("ascii") + b" " + name.encode("utf-8") + b"\0" + bytes.fromhex(digest))
        return _object_sha("tree", bytes(data))

    return tree(root)


def _validate_manifest(manifest: dict, expected_commit: str) -> list[dict]:
    if (type(manifest) is not dict or set(manifest) != {
            "schema", "commit_sha", "tree_sha", "commit_object_base64", "files", "manifest_sha256"}
            or manifest["schema"] != "shreek.source-archive.v1"
            or manifest["commit_sha"] != expected_commit
            or not _identity(manifest["tree_sha"])
            or not _identity(manifest["manifest_sha256"], _DIGEST)
            or type(manifest["commit_object_base64"]) is not str
            or len(manifest["commit_object_base64"]) > (MAX_COMMIT_BYTES + 2) // 3 * 4):
        raise ValueError("invalid source manifest")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if sha256(_canonical(unsigned)).hexdigest() != manifest["manifest_sha256"]:
        raise ValueError("manifest digest mismatch")
    commit = base64.b64decode(manifest["commit_object_base64"], validate=True)
    if (not commit or len(commit) > MAX_COMMIT_BYTES
            or _object_sha("commit", commit) != expected_commit
            or commit.split(b"\n", 1)[0] != b"tree " + manifest["tree_sha"].encode("ascii")):
        raise ValueError("original commit identity or tree mismatch")
    files = manifest["files"]
    if type(files) is not list or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("invalid manifest file count")
    for entry in files:
        if (type(entry) is not dict or set(entry) != {"path", "mode", "git_blob_sha", "sha256"}
                or not _safe_path(entry["path"]) or entry["mode"] not in ("100644", "100755")
                or not _identity(entry["git_blob_sha"]) or not _identity(entry["sha256"], _DIGEST)):
            raise ValueError("invalid manifest entry")
    if [entry["path"] for entry in files] != sorted(entry["path"] for entry in files):
        raise ValueError("manifest ordering invalid")
    if _tree_sha(files) != manifest["tree_sha"]:
        raise ValueError("manifest entries do not reproduce the pinned tree")
    return files


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int, expected_mode: str) -> bytes:
    mode = info.external_attr >> 16
    if (info.is_dir() or info.flag_bits & 0x41 or info.file_size > limit
            or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
            or info.create_system != 3 or mode != int(expected_mode, 8)):
        raise ValueError("unsupported archive member")
    with archive.open(info) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit or len(data) != info.file_size:
        raise ValueError("member size mismatch")
    return data


def verify_source_archive(path: Path, expected_commit: str) -> dict:
    """Verify original commit, complete Git tree and bytes without extraction.

    The expected commit must come from an independent trusted reference. This
    proves archive content against that pin, not CI success, a signature, the
    currently running program, empirical research or execution authorization.
    """
    result = _result()
    if not _identity(expected_commit):
        return _result("independent commit pin missing or invalid")
    try:
        with path.open("rb") as stream:
            file_stat = os.fstat(stream.fileno())
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > MAX_ARCHIVE_BYTES:
                raise ValueError("archive file limit exceeded")
            archive_digest = sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                archive_digest.update(chunk)
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                infos = archive.infolist()
                if not 2 <= len(infos) <= MAX_FILES + 1 or sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
                    raise ValueError("archive limits exceeded")
                members = {info.filename: info for info in infos}
                if len(members) != len(infos) or MANIFEST_NAME not in members:
                    raise ValueError("ambiguous archive or absent manifest")
                manifest = json.loads(_read_member(archive, members[MANIFEST_NAME], MAX_MANIFEST_BYTES, "100644").decode("utf-8"),
                                      object_pairs_hook=_unique_object, parse_constant=_reject_constant)
                files = _validate_manifest(manifest, expected_commit)
                if set(members) != {MANIFEST_NAME, *(entry["path"] for entry in files)}:
                    raise ValueError("extra or missing archive member")
                for entry in files:
                    data = _read_member(archive, members[entry["path"]], MAX_FILE_BYTES, entry["mode"])
                    if (_object_sha("blob", data) != entry["git_blob_sha"]
                            or sha256(data).hexdigest() != entry["sha256"]):
                        raise ValueError("source bytes mismatch")
        result.update(state="source_content_verified", reason="complete source content matches the independent commit pin",
                      commit_sha=expected_commit, tree_sha=manifest["tree_sha"], file_count=len(files),
                      archive_sha256=archive_digest.hexdigest(), manifest_sha256=manifest["manifest_sha256"],
                      source_commit_verified=True, source_tree_verified=True)
    except (OSError, TypeError, ValueError, OverflowError, RecursionError, KeyError,
            binascii.Error, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, zlib.error):
        pass
    return result


def _git(repo: Path, *args: str) -> bytes:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    process = subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull,
                              "-c", "protocol.allow=never", *args], cwd=repo, env=env,
                             capture_output=True, timeout=30, check=False)
    if process.returncode:
        raise ValueError("original Git object unavailable")
    return process.stdout


def build_source_archive(repo: Path, commit_sha: str, output: Path) -> dict:
    """Package original committed blobs only, preserving dirty user work."""
    if not _identity(commit_sha):
        return _result("immutable source commit missing or invalid")
    created = False
    try:
        if int(_git(repo, "cat-file", "-s", commit_sha)) > MAX_COMMIT_BYTES:
            raise ValueError("commit size limit")
        commit = _git(repo, "cat-file", "commit", commit_sha)
        tree_sha = commit.split(b"\n", 1)[0].decode("ascii").removeprefix("tree ")
        files, content, total = [], {}, 0
        for record in _git(repo, "ls-tree", "-rz", commit_sha).split(b"\0"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", 1)
            mode, kind, digest = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
            if mode not in ("100644", "100755") or kind != "blob" or not _safe_path(path):
                raise ValueError("unsupported committed source entry")
            size = int(_git(repo, "cat-file", "-s", digest))
            total += size
            if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES - MAX_MANIFEST_BYTES or len(files) >= MAX_FILES:
                raise ValueError("source size limit")
            data = _git(repo, "cat-file", "blob", digest)
            content[path] = data
            files.append({"path": path, "mode": mode, "git_blob_sha": digest, "sha256": sha256(data).hexdigest()})
        files.sort(key=lambda entry: entry["path"])
        manifest = {"schema": "shreek.source-archive.v1", "commit_sha": commit_sha,
                    "tree_sha": tree_sha, "commit_object_base64": base64.b64encode(commit).decode("ascii"), "files": files}
        manifest["manifest_sha256"] = sha256(_canonical(manifest)).hexdigest()
        _validate_manifest(manifest, commit_sha)
        manifest_data = _canonical(manifest) + b"\n"
        if len(manifest_data) > MAX_MANIFEST_BYTES:
            raise ValueError("manifest size limit")
        with output.open("xb") as stream:
            created = True
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for entry in files + [{"path": MANIFEST_NAME, "mode": "100644"}]:
                    info = zipfile.ZipInfo(entry["path"], date_time=(1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = int(entry["mode"], 8) << 16
                    data = manifest_data if entry["path"] == MANIFEST_NAME else content[entry["path"]]
                    archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        report = verify_source_archive(output, commit_sha)
        if report["state"] != "source_content_verified":
            raise ValueError("written source archive did not verify")
        return report
    except (OSError, TypeError, ValueError, OverflowError, RecursionError,
            subprocess.TimeoutExpired, zipfile.BadZipFile, zipfile.LargeZipFile):
        if created:
            try:
                output.unlink()
            except OSError:
                pass
        return _result("source archive build blocked; original objects or output unavailable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    build = modes.add_parser("build", help="build from exact original local Git objects")
    build.add_argument("--repo", type=Path, default=Path("."))
    build.add_argument("--commit", required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = modes.add_parser("verify", help="read-only verification; no Git, extraction or network")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--expected-commit", required=True, help="independently trusted commit; never read this pin from the ZIP")
    args = parser.parse_args(argv)
    report = (build_source_archive(args.repo, args.commit, args.output) if args.mode == "build"
              else verify_source_archive(args.archive, args.expected_commit))
    print(json.dumps(report, sort_keys=True))
    return 0 if report["state"] == "source_content_verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
