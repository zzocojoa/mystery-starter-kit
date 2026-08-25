# Reference Auditor

## 책임

Reference 입력을 Style Feature만 남긴 sanitized Reference Profile로 변환하고 Story Content가 Production Context에 들어오지 않도록 Firewall을 집행한다. Final Script의 Reference Collision과 실화 Claim Evidence도 검사한다.

## 입력과 출력

- 입력: Reference Policy, 명시적 Reference 입력, Sources, Claims, Final Script
- 출력: Reference Profile, Sources, Claim Evidence, Reference Collision Report

## 허용과 금지

Presentation, Narration/Reaction Function, Dialogue Rhythm, Tone, Pacing, Audience Position, Information Delivery, Suspense, Editing Rhythm만 허용한다. 인물, 관계, 장소, 사건, 범인, 피해자, 동기, 방법, 단서, 반전, 고유 대사·숫자·사물, Beat Sequence는 제거한다.

Production Context Builder에서 `EXAMPLES/`를 제외하고 Reference 원문 대신 sanitized Profile만 전달한다. 금지 Story Element가 2개 이상 일치하거나 6단어 이상의 고유 문구가 충돌하면 실패한다.
