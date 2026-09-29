/**
 * API 서버 주소. 같은 도메인에 nginx 프록시가 있으면 비워 두고(기본), 프론트와 API 를 따로 배포하면
 * VITE_API_URL=https://api.example.com 으로 지정. api/client 와 store/auth 가 함께 쓴다 (서로 import 하면 순환이라 따로 둔다)
 */
export const API_ORIGIN = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''
