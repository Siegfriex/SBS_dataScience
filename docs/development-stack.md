# Development Stack

이 저장소는 데이터사이언스 실습과 일반 개발 실습을 함께 다루기 위해 다음 스택을 초기 설정한다.

## Runtime 기준

| 영역 | 기준 |
| --- | --- |
| Python | 3.12 이상 |
| Node.js | 24.17.0 LTS 권장, Vite 요구사항상 20.19 이상 |
| React | 19.2 계열 |
| Vite | 8.0 계열 |
| Java | 21 권장 |
| Spring Boot | 4.1.0 |
| Maven | 3.6.3 이상 |
| R | Rscript 사용 가능 환경 |

## Node.js / React

```bash
nvm use
npm install
npm run dev:react
```

React 앱 위치:

```text
apps/react-js
```

기본 개발 서버:

```text
http://127.0.0.1:5173
```

## Java / Spring Boot

Java 21과 Maven을 설치한 뒤 실행한다.

```bash
mvn -f apps/spring-boot/pom.xml spring-boot:run
```

기본 API:

```text
GET http://127.0.0.1:8080/api/status
GET http://127.0.0.1:8080/actuator/health
```

## 통합 점검

```bash
npm run check:env
```

Maven이 설치되지 않은 환경에서는 Spring 빌드 명령은 실행되지 않지만, 점검 스크립트가 누락 상태를 표시한다.

## 기준 문서

- Node.js release status: https://nodejs.org/en/about/previous-releases
- Vite guide: https://vite.dev/guide/
- React versions: https://react.dev/versions
- Spring Boot system requirements: https://docs.spring.io/spring-boot/system-requirements.html
