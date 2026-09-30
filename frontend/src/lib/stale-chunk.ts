/**
 * 배포 뒤에도 열어 둔 탭은 예전 조각 파일 이름(해시)을 기억한다. 그 탭에서 처음 여는 화면으로 가면 서버에는
 * 새 이름의 파일만 있어 불러오기가 실패한다("Failed to fetch dynamically imported module", 404).
 * 이때는 페이지를 한 번 새로고침해 새 버전(index.html · 조각 파일)을 받으면 된다.
 * 30초 안에 또 실패하면 새로고침을 반복하지 않고 오류 화면으로 넘긴다 — 정말 서버가 없는 경우의 무한 새로고침 방지.
 */
const KEY = 'hooply-chunk-reload'
const WINDOW_MS = 30_000

// Chrome · Safari · Firefox 가 각각 다른 문구를 쓴다
const CHUNK_ERROR = /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i

export function isChunkLoadError(e: unknown): boolean {
  return CHUNK_ERROR.test(e instanceof Error ? e.message : String(e))
}

/** 새로고침을 시작했으면 true. 방금 새로고침했는데 또 실패했으면 false (호출한 쪽이 오류를 보여 준다). */
export function reloadForNewVersion(): boolean {
  try {
    const last = Number(sessionStorage.getItem(KEY) ?? 0)
    if (Date.now() - last < WINDOW_MS) return false
    sessionStorage.setItem(KEY, String(Date.now()))
  } catch { /* 저장소를 못 쓰면 확인 없이 한 번 새로고침 */ }
  location.reload()
  return true
}
