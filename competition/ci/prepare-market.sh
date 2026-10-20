#!/usr/bin/env bash
# Build the official local test economy. Only the public Anvil test wallet is used.
set -euo pipefail
cd "${1:?usage: prepare-market.sh ERIS_CHECKOUT}"
mkdir -p validation-setup
npm ci --ignore-scripts
forge build
(
  cd deployer
  npm ci --ignore-scripts
  forge build
  cp .env.example .env
  sed -i 's/^MANAGE_ANVIL=.*/MANAGE_ANVIL=false/' .env
  ./scripts/setup-vendors.sh
)
node --import tsx deployer/src/anvil-cli.ts > validation-setup/anvil.log 2>&1 &
anvil_pid=$!
trap 'kill "$anvil_pid" 2>/dev/null || true; wait "$anvil_pid" 2>/dev/null || true' EXIT
ready=false
for _ in $(seq 1 60); do
  if cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [ "$ready" != true ]; then
  cat validation-setup/anvil.log
  exit 1
fi
(
  cd deployer
  node --import tsx src/index.ts --keep-fresh
) 2>&1 | tee validation-setup/deploy.log
node --import tsx scripts/genLocalConstants.ts
node --import tsx scripts/genStateDump.ts
