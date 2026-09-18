/**
 * 카카오 JavaScript SDK 로더 + 카카오톡 공유 (11.2절 "카카오톡 공유"). 키는 VITE_KAKAO_JS_KEY (공개용 키, 도메인으로 보호).
 * SDK 는 필요할 때 한 번만 <script> 로 불러온다. 키가 없거나 로드에 실패하면 OS 공유 시트 → 클립보드 순으로 대체한다.
 */

declare global {
  interface Window {
    Kakao?: {
      isInitialized(): boolean
      init(key: string): void
      Share: {
        sendDefault(opts: Record<string, unknown>): void
        /** 이미지를 카카오 서버에 올려 공유 메시지에 쓸 수 있는 주소를 받는다 (20일 보관). FileList 를 받는다 */
        uploadImage(opts: { file: FileList | File[] }): Promise<{ infos: { original: { url: string; width: number; height: number } } }>
      }
    }
  }
}

const SDK_URL = 'https://t1.kakaocdn.net/kakao_js_sdk/2.7.4/kakao.min.js'
let loading: Promise<boolean> | null = null

export function loadKakao(): Promise<boolean> {
  const key = import.meta.env.VITE_KAKAO_JS_KEY as string | undefined
  if (!key) return Promise.resolve(false)
  if (window.Kakao?.isInitialized()) return Promise.resolve(true)
  if (loading) return loading
  loading = new Promise<boolean>((resolve) => {
    const done = () => { try { if (window.Kakao && !window.Kakao.isInitialized()) window.Kakao.init(key); resolve(!!window.Kakao?.isInitialized()) } catch { resolve(false) } }
    if (window.Kakao) return done()
    const s = document.createElement('script')
    s.src = SDK_URL; s.async = true
    s.onload = done; s.onerror = () => resolve(false)
    document.head.appendChild(s)
  })
  return loading
}

export type ShareResult = 'kakao' | 'sheet' | 'clipboard' | 'download' | 'none'

/** 텍스트 + 링크를 카카오톡으로 공유. 실패하면 OS 공유 시트, 그다음 클립보드. 반환값으로 UI 문구를 정한다 */
export async function shareText(text: string, url: string): Promise<ShareResult> {
  if (await loadKakao()) {
    try {
      window.Kakao!.Share.sendDefault({ objectType: 'text', text, link: { mobileWebUrl: url, webUrl: url } })
      return 'kakao'
    } catch { /* SDK 오류 → 아래로 */ }
  }
  try {
    if (navigator.share) { await navigator.share({ text: `${text}\n${url}` }); return 'sheet' }
  } catch { return 'none' }  // 사용자가 취소
  try { await navigator.clipboard.writeText(`${text}\n${url}`); return 'clipboard' } catch { return 'none' }
}

/** 캔버스로 만든 이미지를 카카오톡 피드 메시지로. SDK 가 없으면 OS 공유 시트(파일), 그것도 없으면 파일로 내려받는다 */
export async function shareImage(file: File, opts: { title: string; description: string; url: string; width: number; height: number }): Promise<ShareResult> {
  const link = { mobileWebUrl: opts.url, webUrl: opts.url }
  if (await loadKakao()) {
    try {
      const files = toFileList(file)
      const { infos } = await window.Kakao!.Share.uploadImage({ file: files })
      window.Kakao!.Share.sendDefault({
        objectType: 'feed',
        content: { title: opts.title, description: opts.description, imageUrl: infos.original.url, imageWidth: opts.width, imageHeight: opts.height, link },
        buttons: [{ title: '앱에서 보기', link }],
      })
      return 'kakao'
    } catch { /* 업로드·SDK 오류 → 아래로 */ }
  }
  try {
    if (navigator.canShare?.({ files: [file] })) { await navigator.share({ files: [file], title: opts.title, text: `${opts.description}\n${opts.url}` }); return 'sheet' }
  } catch { return 'none' }  // 사용자가 취소
  return downloadFile(file) ? 'download' : 'none'
}

/** Kakao SDK 의 uploadImage 는 <input type=file> 의 FileList 를 기대한다. 캔버스에서 만든 File 은 DataTransfer 로 감싼다 */
function toFileList(file: File): FileList | File[] {
  try {
    const dt = new DataTransfer()
    dt.items.add(file)
    return dt.files
  } catch { return [file] }
}

function downloadFile(file: File): boolean {
  try {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(file)
    a.download = file.name
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(a.href), 10_000)
    return true
  } catch { return false }
}

export const SHARE_DONE: Record<ShareResult, string | null> = {
  kakao: '카카오톡으로 보냈어요.',
  sheet: '공유 시트를 열었어요.',
  clipboard: '복사했어요. 카카오톡에 붙여 넣어 주세요.',
  download: '이미지를 저장했어요. 카카오톡에 첨부해 주세요.',
  none: null,
}
