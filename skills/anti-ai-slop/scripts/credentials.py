#!/usr/bin/env python3
"""Find API keys where people already keep them, and remember where, never what.

A key source is a short string:

    env:GEMINI_API_KEY               an environment variable
    keychain:my-llm-key              a macOS Keychain item, by service name
    keychain:my-llm-key@my-account   the same, narrowed to one account
    file:~/.config/litellm/key       the first line of a file
    op://Private/LiteLLM/credential  a 1Password secret reference (needs the op CLI)

The saved setup holds sources and gateway URLs only. Key values are read at run
time, used inside the calling process, and never printed, logged, or written out.
"""

import json
import os
import stat
import subprocess
import sys
from urllib.parse import urlparse


class CredentialError(Exception):
    """Raised with a message that is safe to show: it never contains a key value."""


def config_path():
    return os.path.expanduser(os.environ.get("ANTI_SLOP_CONFIG", "~/.config/anti-ai-slop/config.json"))


def resolve(source, timeout=15):
    if not source:
        raise CredentialError("no key source given")
    if source.startswith("op://"):
        return _run(["op", "read", source], "1Password reference", timeout)

    kind, sep, ref = source.partition(":")
    if not sep or not ref:
        raise CredentialError(
            "unrecognized key source {!r}: use env:, keychain:, file:, or op://".format(source))

    if kind == "env":
        value = os.environ.get(ref, "").strip()
        if not value:
            raise CredentialError("environment variable {} is not set".format(ref))
        return value

    if kind == "keychain":
        if sys.platform != "darwin":
            raise CredentialError("keychain: sources only work on macOS")
        service, _, account = ref.partition("@")
        cmd = ["security", "find-generic-password", "-s", service]
        if account:
            cmd += ["-a", account]
        return _run(cmd + ["-w"], "Keychain item {!r}".format(ref), timeout)

    if kind == "file":
        path = os.path.expanduser(ref)
        if not os.path.isfile(path):
            raise CredentialError("no key file at {}".format(path))
        if os.stat(path).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            sys.stderr.write("warning: {} is readable by other users; run chmod 600 on it\n".format(path))
        with open(path, encoding="utf-8") as fh:
            value = fh.readline().strip()
        if not value:
            raise CredentialError("key file {} is empty".format(path))
        return value

    raise CredentialError(
        "unrecognized key source type {!r}: use env:, keychain:, file:, or op://".format(kind))


def _run(cmd, label, timeout):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise CredentialError("cannot read {}: {} is not installed".format(label, cmd[0]))
    except subprocess.TimeoutExpired:
        raise CredentialError("timed out reading {}".format(label))
    value = proc.stdout.strip()
    if proc.returncode != 0 or not value:
        # stdout and stderr stay out of the message: either could hold the secret.
        raise CredentialError("could not read {} (exit code {})".format(label, proc.returncode))
    return value


def check_url(url):
    """A gateway key must not travel in the clear, except to this machine."""
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return url.rstrip("/")
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        return url.rstrip("/")
    raise CredentialError("gateway URL must use https (http only for localhost): {}".format(url))


def load_config():
    path = config_path()
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except ValueError:
        raise CredentialError("setup file {} is not valid JSON".format(path))


def save_config(cfg):
    path = config_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path
