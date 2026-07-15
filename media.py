"""
媒体文件处理模块：CDN 下载、AES-128-ECB 解密、图片处理、SILK 语音转换。
"""

import base64
import io
import struct
from typing import Optional, Tuple

import aiohttp
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from PIL import Image

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
MAX_IMAGE_DIMENSION = 2048       # 图片长边最大像素
JPEG_QUALITY = 85                # JPEG 输出质量
MAX_DOWNLOAD_SIZE = 10 * 1024 * 1024  # 下载文件最大 10 MB


# ===================================================================
# AES Key 解析
# ===================================================================

def parse_aes_key(aes_key_str: str) -> bytes:
    """解析多种格式的 aes_key，统一返回 16 字节原始密钥。

    微信 iLink 的 aes_key 可能以三种格式出现：
      - 格式 A：32 字符 hex 字符串（常见于 image_item.aeskey）
      - 格式 B：base64(32字符hex字符串的ascii)（常见于 media.aes_key）
      - 格式 C：base64(原始16字节)（少见）

    按优先级依次尝试解析。
    """
    if not aes_key_str:
        raise ValueError("aes_key 为空")

    # 格式 A：32 字符纯 hex
    if len(aes_key_str) == 32 and all(c in "0123456789abcdefABCDEF" for c in aes_key_str):
        return bytes.fromhex(aes_key_str)

    # 尝试 base64 解码
    try:
        decoded = base64.b64decode(aes_key_str)
    except Exception:
        raise ValueError(f"无法解析 aes_key（非 hex 也非 base64）: {aes_key_str[:50]}...")

    # 解码后恰好 16 字节 → 格式 C（原始密钥）
    if len(decoded) == 16:
        return decoded

    # 解码后 32 字节 → 格式 B（hex 字符串的 ascii）
    if len(decoded) == 32:
        text = decoded.decode("ascii", errors="ignore")
        if all(c in "0123456789abcdefABCDEF" for c in text):
            return bytes.fromhex(text)

    raise ValueError(f"未知 aes_key 格式，解码后 {len(decoded)} 字节: {decoded[:20]!r}...")


# ===================================================================
# AES-128-ECB 加解密
# ===================================================================

def aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 解密，自动去除 PKCS7 padding。"""
    if len(key) != 16:
        raise ValueError(f"AES key 必须为 16 字节，实际 {len(key)} 字节")

    cipher = AES.new(key, AES.MODE_ECB)
    padded = cipher.decrypt(ciphertext)
    try:
        return unpad(padded, AES.block_size)
    except ValueError:
        # 部分 CDN 文件可能无 padding（恰好对齐），返回原始解密结果
        return padded


def aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 加密（PKCS7 padding），用于上传媒体到 CDN。"""
    from Crypto.Util.Padding import pad
    if len(key) != 16:
        raise ValueError(f"AES key 必须为 16 字节，实际 {len(key)} 字节")
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(pad(plaintext, AES.block_size))


def decrypt_cdn_media(ciphertext: bytes, aes_key: str) -> bytes:
    """下载自 CDN 的密文 → AES-128-ECB 解密 → 明文。

    封装了 aes_key 格式解析 + AES 解密，一步完成。
    """
    key = parse_aes_key(aes_key)
    return aes_ecb_decrypt(ciphertext, key)


# ===================================================================
# CDN 下载
# ===================================================================

async def download_media(
    session: aiohttp.ClientSession,
    url: str,
    max_size: int = MAX_DOWNLOAD_SIZE,
    timeout: int = 30,
) -> Optional[bytes]:
    """从 CDN 下载文件，带大小和时间限制，失败返回 None。"""
    if not url:
        return None
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return None
            data = bytearray()
            async for chunk in resp.content.iter_chunked(8192):
                data.extend(chunk)
                if len(data) > max_size:
                    return None
            return bytes(data)
    except Exception:
        return None


async def download_and_decrypt(
    session: aiohttp.ClientSession,
    full_url: str,
    aes_key: str,
) -> Optional[bytes]:
    """下载 CDN 加密文件并解密，一步完成。失败返回 None。"""
    ciphertext = await download_media(session, full_url)
    if ciphertext is None:
        return None
    try:
        return decrypt_cdn_media(ciphertext, aes_key)
    except Exception as e:
        print(f"[media] 解密失败: {e}")
        return None


# ===================================================================
# 图片处理（给 vision API 用）
# ===================================================================

def process_image_for_vision(
    image_bytes: bytes,
    max_dim: int = MAX_IMAGE_DIMENSION,
    quality: int = JPEG_QUALITY,
) -> Tuple[str, str]:
    """将图片 bytes 处理为适合 vision API 的 (mime_type, base64_str)。

    - 透明图片（表情包）填白底转 RGB
    - 长边缩放到 max_dim
    - 统一输出 JPEG 格式的 base64（不带 data: URI 前缀）
    """
    img = Image.open(io.BytesIO(image_bytes))

    # 透明通道处理：RGBA / P / LA → 白底 RGB
    if img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode == "LA":
            img = img.convert("RGBA")
        if img.mode == "RGBA":
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # 缩放
    w, h = img.size
    if w > max_dim or h > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # JPEG 编码
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    jpeg_bytes = buf.getvalue()

    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    return "image/jpeg", b64


# ===================================================================
# 构建 AI API 的 image content block
# ===================================================================

def build_image_block_openai(mime_type: str, b64_data: str) -> dict:
    """构建 OpenAI/DeepSeek 兼容的 image_url content block。"""
    data_uri = f"data:{mime_type};base64,{b64_data}"
    return {
        "type": "image_url",
        "image_url": {"url": data_uri},
    }


def build_image_block_anthropic(mime_type: str, b64_data: str) -> dict:
    """构建 Anthropic 兼容的 image content block（裸 base64，不带前缀）。"""
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": b64_data,
        },
    }


# ===================================================================
# 工具函数
# ===================================================================

def detect_image_format(data: bytes) -> str:
    """根据文件头检测图片格式，返回 MIME type。"""
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] in (b"RIFF", b"WEBP"):
        return "image/webp"
    return "image/jpeg"  # 默认


def get_encrypted_size(raw_size: int, block_size: int = 16) -> int:
    """计算 PKCS7 填充后的加密文件大小（始终为 16 的倍数）。"""
    return ((raw_size // block_size) + 1) * block_size


# ===================================================================
# SILK 语音解码
# ===================================================================

def silk_to_wav(silk_data: bytes, sample_rate: int = 16000) -> Optional[bytes]:
    """将 WeChat SILK v3 音频解码为 WAV 格式。

    尝试使用 pilk 库；不可用时返回 None。
    WeChat SILK 文件以 \\x02 前缀开头，pilk 默认支持。
    """
    try:
        import pilk
    except ImportError:
        print("[media] pilk 未安装，无法解码 SILK 语音；请 pip install pilk")
        return None

    try:
        pcm_data = pilk.decode(silk_data)
        return _pcm_to_wav(pcm_data, sample_rate=sample_rate)
    except Exception as e:
        print(f"[media] SILK 解码失败: {e}")
        return None


def _pcm_to_wav(pcm: bytes, sample_rate: int = 16000, channels: int = 1, bits: int = 16) -> bytes:
    """将原始 PCM 数据封装为 WAV 格式。"""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    data_size = len(pcm)

    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))  # 文件总长 - 8
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))               # fmt chunk 长度
    buf.write(struct.pack("<H", 1))                 # PCM = 1
    buf.write(struct.pack("<H", channels))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", byte_rate))
    buf.write(struct.pack("<H", block_align))
    buf.write(struct.pack("<H", bits))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(pcm)
    return buf.getvalue()
