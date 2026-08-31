#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

IMAGE="${IMAGE:-idp-db-backupper:local}"
KIND_CLUSTER="${KIND_CLUSTER:-idp-db-backupper}"
DEPLOY_NAMESPACE="${DEPLOY_NAMESPACE:-idp-db-backupper}"
DEPLOY_KUSTOMIZE="${DEPLOY_KUSTOMIZE:-k8s/deploy}"

usage() {
  cat <<EOF
usage: ./dev.sh <command>

commands:
  wizard             guided local setup
  dev                uv sync --dev
  setup              full local setup (k8s + seed)
  test               lint + typecheck + unit tests
  test-integration   integration tests (needs k8s)
  smoke              daily backup + list + status
  lint               ruff check + format check
  format             ruff format
  build              uv build + docker image
  clean              k8s-down (ignore errors)
  k8s-up             start cluster workloads
  k8s-down           stop cluster workloads
  docker-build       build image (cached deps layer)
  docker-load        load image into kind
  docker             build + load
  publish [tag]      local kind rolling deploy (dev)
  ci-publish-deploy  deploy CI image to platform cluster via kubectl
  ci-lint            CI lint job
  ci-build           CI build job (+ push to ghcr.io on main)
  ci-test            CI unit test job
  ci-coverage        CI coverage job (unit tests + coverage report)
  ci-integration     CI integration job (needs kind + docker image)
EOF
}

step() {
  echo
  echo "==> $1"
}

have() {
  command -v "$1" >/dev/null 2>&1
}

confirm() {
  local prompt="$1"
  local default="${2:-y}"
  local hint reply

  if [[ "$default" == "y" ]]; then
    hint="Y/n"
  else
    hint="y/N"
  fi

  read -r -p "$prompt [$hint] " reply
  reply="${reply:-$default}"
  [[ "$reply" =~ ^[Yy] ]]
}

sync_deps() {
  if [[ "${LOCKED:-}" == "1" ]]; then
    uv sync --dev --locked "$@"
  else
    uv sync --dev "$@"
  fi
}

install_pg_client() {
  if have pg_dump; then
    return
  fi
  if [[ -f /etc/debian_version ]] && have apt-get; then
    sudo apt-get update
    sudo apt-get install -y postgresql-client
  fi
}

docker_build() {
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    docker buildx build \
      --tag "$IMAGE" \
      --load \
      --cache-from type=gha \
      --cache-to type=gha,mode=max \
      .
    return
  fi
  DOCKER_BUILDKIT=1 docker build -t "$IMAGE" .
}

kind_cluster_exists() {
  have kind && kind get clusters 2>/dev/null | grep -qx "$KIND_CLUSTER"
}

publish_tag() {
  if [[ -n "${PUBLISH_TAG:-}" ]]; then
    echo "$PUBLISH_TAG"
    return
  fi
  if have git; then
    git rev-parse --short HEAD 2>/dev/null && return
  fi
  echo "local"
}

wait_k8s_ready() {
  kubectl wait -n "$DEPLOY_NAMESPACE" \
    --for=condition=ready pod \
    -l app.kubernetes.io/part-of=idp-db-backupper \
    --timeout=180s
}

wait_backupper_ready() {
  kubectl wait -n "$DEPLOY_NAMESPACE" \
    --for=condition=ready pod \
    -l app=backupper \
    --timeout=180s
}

ensure_host_dotenv() {
  if [[ ! -f backupper.toml ]]; then
    uv run python -c "from config import ensure_dev_config; ensure_dev_config()"
  fi
  if [[ ! -f .env ]]; then
    cp .env.example .env
  fi
}

prepare_dev_cluster() {
  ensure_host_dotenv
  uv run python -c "from db.dev_schema import apply_dev_schema; apply_dev_schema()"
  uv run python -c "from config import load_config; from storage import s3; s3.ensure_bucket(load_config())"
}

publish_smoke_job() {
  local job="db-backupper-smoke-$(date +%s)"
  local secret_name="backupper-secrets"
  local service_account=""
  if [[ "${PUBLISH_TARGET:-local}" == "local" ]]; then
    secret_name="backupper-env"
  else
    service_account="      serviceAccountName: backupper"
  fi
  kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${job}
  namespace: ${DEPLOY_NAMESPACE}
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
${service_account}
      containers:
        - name: backupper
          image: ${IMAGE}
          imagePullPolicy: IfNotPresent
          command: ["python", "manage.py", "backup"]
          env:
            - name: BACKUPPER_CONFIG
              value: /etc/backupper/backupper.toml
          envFrom:
            - secretRef:
                name: ${secret_name}
                optional: true
          volumeMounts:
            - name: config
              mountPath: /etc/backupper
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: backupper-config
EOF
  kubectl wait -n "$DEPLOY_NAMESPACE" \
    --for=condition=complete \
    "job/${job}" \
    --timeout=300s
  kubectl logs -n "$DEPLOY_NAMESPACE" "job/${job}"
  kubectl delete job "${job}" -n "$DEPLOY_NAMESPACE" --ignore-not-found
}

rollout_deploy() {
  kubectl set image "deployment/backupper" "backupper=${IMAGE}" -n "$DEPLOY_NAMESPACE"

  if ! kubectl rollout status "deployment/backupper" -n "$DEPLOY_NAMESPACE" --timeout=300s; then
    echo "rollout of ${IMAGE} failed to become ready — rolling back" >&2
    kubectl rollout undo "deployment/backupper" -n "$DEPLOY_NAMESPACE"
    kubectl rollout status "deployment/backupper" -n "$DEPLOY_NAMESPACE" --timeout=180s
    echo "rolled back deployment/backupper in ${DEPLOY_NAMESPACE} to the previous revision" >&2
    return 1
  fi

  kubectl annotate deployment/backupper -n "$DEPLOY_NAMESPACE" \
    "backupper.dev/deployed-at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "backupper.dev/image=${IMAGE}" \
    --overwrite
}

deploy_remote() {
  if [[ -z "${IMAGE:-}" ]]; then
    echo "IMAGE is required — use the registry ref built by CI (e.g. ghcr.io/org/idp-db-backupper:abc123)" >&2
    exit 1
  fi

  kubectl apply -k "$DEPLOY_KUSTOMIZE"
  rollout_deploy

  echo "deployed ${IMAGE} → ${DEPLOY_NAMESPACE} (rolling update complete)"

  if [[ "${RUN_SMOKE:-1}" == "1" || "${RUN_SMOKE:-1}" == "true" ]]; then
    publish_smoke_job
  fi
}

deploy_local() {
  local tag
  tag="$(publish_tag)"
  IMAGE="idp-db-backupper:${tag}"
  export IMAGE

  if ! kind_cluster_exists; then
    echo "kind cluster '$KIND_CLUSTER' not found — run ./dev.sh wizard first" >&2
    exit 1
  fi

  LOCKED=1 sync_deps
  uv build
  docker_build
  kind load docker-image "$IMAGE" --name "$KIND_CLUSTER"

  DEPLOY_KUSTOMIZE=k8s
  kubectl apply -k "$DEPLOY_KUSTOMIZE"
  wait_k8s_ready
  prepare_dev_cluster
  rollout_deploy
  wait_backupper_ready

  echo "published ${IMAGE} → kind/${KIND_CLUSTER} (rolling update complete)"

  if [[ "${RUN_SMOKE:-1}" == "1" || "${RUN_SMOKE:-1}" == "true" ]]; then
    publish_smoke_job
  fi
}

run_publish() {
  if [[ "${PUBLISH_TARGET:-local}" == "remote" ]]; then
    deploy_remote "$@"
  else
    deploy_local "$@"
  fi
}

ci_publish_deploy() {
  deploy_remote "$@"
}

wizard() {
  local total=7
  local missing=0

  step "1/$total Check prerequisites"
  for cmd in uv kubectl docker kind; do
    if have "$cmd"; then
      echo "  ok $cmd"
    else
      echo "  missing $cmd"
      missing=1
    fi
  done

  if ! have pg_dump; then
    echo "  note: postgresql-client not found (needed for integration tests / pg_dump backups on host)"
  fi

  if (( missing )); then
    echo
    echo "Install the missing tools above, then run ./dev.sh wizard again."
    exit 1
  fi

  step "2/$total Install Python dependencies"
  sync_deps

  step "3/$total kind cluster"
  if kind_cluster_exists; then
    echo "  cluster '$KIND_CLUSTER' already exists"
  elif confirm "Create kind cluster '$KIND_CLUSTER'?"; then
    kind create cluster --name "$KIND_CLUSTER" --config k8s/kind-config.yaml
  else
    echo "  skipped — you'll need a cluster before k8s workloads can start"
  fi

  step "4/$total Configure .env and start workloads"
  local setup_args=(--seed)
  if [[ -f .env ]]; then
    if confirm "Overwrite existing .env?"; then
      setup_args+=(--force)
    else
      echo "  keeping existing .env"
      setup_args=()
    fi
  fi

  if ((${#setup_args[@]})); then
    uv run python manage.py setup "${setup_args[@]}"
  else
    if confirm "Apply k8s manifests and wait for pods?"; then
      uv run python manage.py k8s-up
    fi
    if confirm "Seed sample data?"; then
      uv run python manage.py seed
    fi
  fi

  step "5/$total Docker image (for the backupper Deployment)"
  if confirm "Build and load $IMAGE into kind?" "n"; then
    docker_build
    kind load docker-image "$IMAGE" --name "$KIND_CLUSTER"
  else
    echo "  skipped — run ./dev.sh docker later if you need the workload image"
  fi

  step "6/$total Smoke test"
  if confirm "Run a daily backup now?"; then
    smoke
  else
    echo "  skipped"
  fi

  step "7/$total Done"
  cat <<EOF

Local services:
  postgres    localhost:30433
  localstack  localhost:30456
  grafana     localhost:30300  (admin / admin)
  prometheus  localhost:30909

Useful commands:
  uv run python manage.py daily
  uv run python manage.py list
  ./dev.sh test
  ./dev.sh test-integration

EOF
}

run_lint() {
  uv run ruff check .
  uv run ruff format --check .
}

run_build() {
  uv build
  docker_build
}

run_test() {
  run_lint
  uv run mypy src tests
  uv run pytest -q -m "not integration" "$@"
}

run_test_integration() {
  RUN_INTEGRATION=1 uv run pytest -q -m integration "$@"
}

run_smoke() {
  uv run python manage.py daily
  uv run python manage.py list
  uv run python manage.py status
}

ci_lint() {
  LOCKED=1 sync_deps
  run_lint "$@"
}

ci_build() {
  LOCKED=1 sync_deps
  uv build
  local tag
  tag="$(publish_tag)"
  IMAGE="idp-db-backupper:${tag}"
  export IMAGE
  docker_build
  docker tag "$IMAGE" idp-db-backupper:local

  if [[ -n "${IMAGE_REGISTRY:-}" ]]; then
    if [[ "${GITHUB_REF:-}" == "refs/heads/main" || "${GITHUB_EVENT_NAME:-}" == "workflow_dispatch" ]]; then
      REMOTE_IMAGE="$(echo "${IMAGE_REGISTRY}" | tr '[:upper:]' '[:lower:]'):${tag}"
      docker tag "$IMAGE" "$REMOTE_IMAGE"
      docker push "$REMOTE_IMAGE"
      echo "pushed ${REMOTE_IMAGE}"
    fi
  fi
}

ci_test() {
  LOCKED=1 sync_deps
  uv run mypy src tests
  uv run pytest -q -m "not integration" "$@"
}

ci_coverage() {
  LOCKED=1 sync_deps
  uv run pytest -q -m "not integration" --cov --cov-report=term-missing --cov-report=xml "$@"
}

ci_integration() {
  install_pg_client
  LOCKED=1 sync_deps
  if [[ "${SKIP_DOCKER_BUILD:-}" != "1" ]]; then
    docker_build
  fi
  if kind_cluster_exists; then
    kind load docker-image idp-db-backupper:local --name "$KIND_CLUSTER"
  fi
  uv run python manage.py setup -y --force
  run_test_integration
  run_smoke
}

cmd="${1:-}"
shift || true

case "$cmd" in
  wizard)
    wizard "$@"
    ;;
  dev)
    sync_deps "$@"
    ;;
  setup)
    uv run python manage.py setup -y --force --seed "$@"
    ;;
  test)
    run_test "$@"
    ;;
  test-integration)
    run_test_integration "$@"
    ;;
  smoke)
    run_smoke "$@"
    ;;
  ci-lint)
    ci_lint "$@"
    ;;
  ci-build)
    ci_build "$@"
    ;;
  ci-test)
    ci_test "$@"
    ;;
  ci-coverage)
    ci_coverage "$@"
    ;;
  ci-integration)
    ci_integration "$@"
    ;;
  lint)
    LOCKED=1 sync_deps
    run_lint "$@"
    ;;
  format)
    uv run ruff format . "$@"
    ;;
  build)
    sync_deps
    run_build "$@"
    ;;
  clean)
    uv run python manage.py k8s-down "$@" || true
    ;;
  k8s-up)
    uv run python manage.py k8s-up "$@"
    ;;
  k8s-down)
    uv run python manage.py k8s-down "$@"
    ;;
  docker-build)
    docker_build "$@"
    ;;
  docker-load)
    kind load docker-image "$IMAGE" --name "$KIND_CLUSTER" "$@"
    ;;
  docker)
    docker_build
    kind load docker-image "$IMAGE" --name "$KIND_CLUSTER"
    ;;
  publish)
    if [[ $# -gt 0 ]]; then
      PUBLISH_TAG="$1"
      shift
    fi
    run_publish "$@"
    ;;
  ci-publish-deploy)
    ci_publish_deploy "$@"
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    echo "unknown command: $cmd" >&2
    usage >&2
    exit 1
    ;;
esac
