# Cloud Run 자동 배포 (GitHub Actions)

`.github/workflows/deploy-cloudrun.yml`은 `main`에 푸시될 때마다 테스트를 실행하고, `Dockerfile.chatgpt` 이미지를 빌드해 Cloud Run 서비스 `budongsan-tax`(리전 `asia-northeast3`)에 배포한다. Actions 탭에서 수동으로 실행할 수도 있다(Run workflow).

## 1회 준비 (Google Cloud Shell에서 실행)

[Cloud Shell](https://shell.cloud.google.com)을 열고, 상단에서 서비스가 있는 프로젝트를 선택한 뒤 아래를 붙여 넣는다.

```bash
PROJECT=$(gcloud config get-value project)
REGION=asia-northeast3
SA=github-deployer@${PROJECT}.iam.gserviceaccount.com

gcloud services enable run.googleapis.com artifactregistry.googleapis.com iam.googleapis.com
gcloud artifacts repositories create budongsan-tax --repository-format=docker --location=$REGION 2>/dev/null || true
gcloud iam service-accounts create github-deployer --display-name="GitHub Actions deployer" 2>/dev/null || true
for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:$SA" --role=$ROLE --condition=None --quiet >/dev/null
done
gcloud iam service-accounts keys create key.json --iam-account=$SA
cat key.json
```

마지막에 출력된 JSON 전체를 복사한 뒤 `rm key.json`으로 지운다.

## GitHub Secrets 등록

저장소 → Settings → Secrets and variables → Actions → New repository secret

| 이름 | 값 |
|---|---|
| `GCP_SA_KEY` | 위에서 복사한 JSON 전체 |
| `USAGE_SALT` | 사용량 로그용 salt (`docs/USAGE_METRICS.md` 참고). 한 번 정하면 바꾸지 않는다. |

`GCP_SA_KEY`가 없으면 배포 작업은 건너뛰고 성공으로 끝난다.

## 확인

Actions 탭 → `deploy-cloudrun` → Run workflow로 실행한다. 마지막 단계에 서비스 URL이 출력되면 배포가 끝난 것이다. 이후 ChatGPT에서 도구를 한 번 호출하고 Logs Explorer에서 `jsonPayload.event="tool_call"`로 검색해 로그가 보이는지 확인한다.

키를 교체할 때는 새 키를 만들어 Secret을 갱신하고, 이전 키는 `gcloud iam service-accounts keys list/delete --iam-account=$SA`로 삭제한다.
