/**
 * 프로필 사진 전처리 — 원본은 몇 MB 라 그대로 보내면 느리고 DB 도 커진다.
 * 가운데를 정사각으로 잘라 256px JPEG(보통 20~50KB)로 줄여 데이터 URL 로 만든다.
 */

export const AVATAR_SIZE = 256

export async function toAvatarDataUrl(file: File, size = AVATAR_SIZE): Promise<string> {
  if (!file.type.startsWith('image/')) throw new Error('사진 파일만 올릴 수 있어요.')
  const bitmap = await createImageBitmap(file).catch(() => { throw new Error('사진을 읽지 못했어요. 다른 사진으로 시도해 주세요.') })
  try {
    const side = Math.min(bitmap.width, bitmap.height)          // 가운데 정사각 크롭
    const sx = (bitmap.width - side) / 2
    const sy = (bitmap.height - side) / 2
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = size
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('사진을 처리하지 못했어요.')
    ctx.drawImage(bitmap, sx, sy, side, side, 0, 0, size, size)
    return canvas.toDataURL('image/jpeg', 0.85)
  } finally {
    bitmap.close?.()
  }
}
