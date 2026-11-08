from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes
from pathlib import Path


class SecretStoreError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


class WindowsSecretStore:
    """User-bound DPAPI storage for a single DeepSeek API key."""

    def __init__(self, path: str | Path | None = None):
        if os.name != "nt":
            raise SecretStoreError("WindowsSecretStore 仅支持 Windows")
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        self.path = Path(path) if path else base / "CodeAgent" / "deepseek-key.dpapi"

    @staticmethod
    def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
        buffer = ctypes.create_string_buffer(data, len(data))
        blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        return blob, buffer

    @staticmethod
    def _transform(data: bytes, protect: bool) -> bytes:
        source, keepalive = WindowsSecretStore._blob(data)
        output = _DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DataBlob),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if protect:
            ok = crypt32.CryptProtectData(ctypes.byref(source), "CodeAgent DeepSeek API Key", None, None, None, 1, ctypes.byref(output))
        else:
            ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
        _ = keepalive
        if not ok:
            raise SecretStoreError(f"Windows DPAPI 操作失败，错误码 {ctypes.get_last_error()}")
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            kernel32.LocalFree(output.pbData)

    def save(self, secret: str) -> None:
        if not secret:
            self.delete()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        protected = self._transform(secret.encode("utf-8"), protect=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_bytes(base64.b64encode(protected))
        os.replace(temporary, self.path)

    def load(self) -> str | None:
        if not self.path.exists():
            return None
        try:
            protected = base64.b64decode(self.path.read_bytes(), validate=True)
            return self._transform(protected, protect=False).decode("utf-8")
        except Exception as exc:
            raise SecretStoreError("保存的 API Key 无法解密，请重新输入") from exc

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise SecretStoreError(f"无法删除已保存的 API Key：{exc}") from exc
