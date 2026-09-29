"""한국어 조사를 앞말 받침에 맞춘다 — 이름을 나중에 끼워 넣는 문장(AI 설명 복원 · 전술 대안)에서 쓴다.

프론트 `frontend/src/lib/josa.ts` 와 같은 규칙이다.
"""

import re

# (받침 있을 때, 없을 때)
_PAIRS = {p: pair for pair in [("이", "가"), ("은", "는"), ("을", "를"), ("과", "와"), ("으로", "로")] for p in pair}
# 바로 뒤에 붙은 조사. 보조사(는·도·만·의·요)가 한 글자 더 붙은 겹조사("와는")까지. 다음 글자가 한글이면 조사가 아니라 낱말
PARTICLE = r"(?:(으로|로|이|가|은|는|을|를|과|와)(?=(?:는|도|만|의|요)?(?![가-힣])))"


def josa(word: str, particle: str) -> str:
    """이/가 · 은/는 · 을/를 · 과/와 · 으로/로 를 word 의 마지막 글자 받침에 맞춘다. 한글로 끝나지 않으면 그대로."""
    pair = _PAIRS.get(particle)
    last = word[-1:] if word else ""
    if pair is None or not ("가" <= last <= "힣"):
        return particle
    final = (ord(last) - 0xAC00) % 28  # 0 = 받침 없음, 8 = ㄹ
    if pair[0] == "으로":
        return "로" if final in (0, 8) else "으로"
    return pair[0] if final else pair[1]


def substitute(text: str, token: str, lookup) -> str:
    """text 안의 token 정규식(그룹 1 = 키)을 lookup(키) 로 바꾸고, 바로 뒤 조사를 바뀐 말의 받침에 맞춘다.

    lookup 이 None 을 돌려주면 원문 그대로 둔다.
    """
    pat = re.compile(token + PARTICLE + "?")

    def rep(m: re.Match[str]) -> str:
        word = lookup(m.group(1))
        if word is None:
            return m.group(0)
        return word + (josa(word, m.group(2)) if m.group(2) else "")

    return pat.sub(rep, text)
