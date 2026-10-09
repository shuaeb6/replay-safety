#!/usr/bin/env bash
# Deploy live/ to the team namespace at Ingress path /app.
# Reads /config/<team>.config and the process environment. Never prints secret values.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
mapfile -t TEAM_CONFIGS < <(find /config -maxdepth 1 -type f -name '*.config' | sort)
(( ${#TEAM_CONFIGS[@]} == 1 )) || { echo "expected exactly one /config/*.config"; exit 1; }
TEAM_CONFIG="${TEAM_CONFIGS[0]}"

NS=$(grep '^USERNAME=' "$TEAM_CONFIG" | cut -d= -f2-)
[[ "$NS" =~ ^team-[0-9]+$ ]] || { echo "team config USERNAME is not team-<number>"; exit 1; }
export KUBECONFIG="/config/${NS}-k8s.yaml"
[[ -f "$KUBECONFIG" ]] || { echo "missing kubeconfig for ${NS}"; exit 1; }

TEAM_N="${NS#team-}"
APP_HOST="video-lab-team-${TEAM_N}.cosmos.vastdata.com"
APP=replay-safety

echo "Deploying ${APP} in ${NS}"

files=(main.py compiler.py lane.py index.html style.css app.js engine.js match.js catalog.json)
args=()
for name in "${files[@]}"; do
  path="${ROOT}/live/${name}"
  [[ -f "$path" ]] || { echo "missing live/${name}"; exit 1; }
  args+=(--from-file="${name}=${path}")
done
kubectl -n "$NS" create configmap "${APP}-code" "${args[@]}" --dry-run=client -o yaml | kubectl apply -f -

python3 - "$TEAM_CONFIG" "$NS" "$APP" << 'PY'
import os, subprocess, sys

config_path, namespace, app = sys.argv[1:]
wanted = {
    "VSS_URL": "INGRESS_URL",
    "VSS_USERNAME": "USERNAME",
    "VSS_PASSWORD": "PASSWORD",
    "WANDB_API_KEY": "WANDB_API_KEY",
    "WANDB_TEAM": "WANDB_TEAM",
    "WANDB_PROJECT": "WANDB_PROJECT",
    "GPU_BEARER_TOKEN": "GPU_BEARER_TOKEN",
}
file_values = {}
for line in open(config_path, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.removeprefix("export ").strip()
    file_values[key] = value.strip().strip("\"'")

resolved = {}
missing = []
for secret_key, source in wanted.items():
    value = os.environ.get(source) or file_values.get(source) or ""
    if not value:
        missing.append(source)
    else:
        resolved[secret_key] = value
# The public ingress hostname is only resolvable on the workshop VM.
# Pods must call the video backend Service in this namespace.
resolved["VSS_URL"] = "http://video-backend-service:8000"
if missing:
    print("Leaving the existing secret in place. Missing: " + ", ".join(missing))
    sys.exit(0)

cmd = [
    "kubectl", "-n", namespace, "create", "secret", "generic", f"{app}-vss-creds",
    "--dry-run=client", "-o", "yaml",
]
for key, value in resolved.items():
    cmd.append(f"--from-literal={key}={value}")
created = subprocess.run(cmd, check=True, capture_output=True)
applied = subprocess.run(["kubectl", "apply", "-f", "-"], input=created.stdout, check=True, capture_output=True)
print(applied.stdout.decode().strip())
PY

sed "s/__APP_HOST__/${APP_HOST}/g" "${ROOT}/deploy/live-app.yaml" | kubectl -n "$NS" apply -f -
kubectl -n "$NS" rollout restart "deploy/${APP}"
kubectl -n "$NS" rollout status "deploy/${APP}" --timeout=180s

health=$(curl -sS -o /dev/null -w '%{http_code}' "http://${APP_HOST}/app/health")
echo "health ${health}"
[[ "$health" == "200" ]] || exit 1
curl -sS "http://${APP_HOST}/app/api/status" | python3 -c '
import json, sys
data = json.load(sys.stdin)
print("mode={mode} archive={archive} wandb={wandb} cosmos={cosmos}".format(**data))
'
