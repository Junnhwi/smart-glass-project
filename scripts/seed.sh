#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-infra/compose/docker-compose.prod.yml}"

docker compose -f "$COMPOSE_FILE" run --rm admin-bootstrap
