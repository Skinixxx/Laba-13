#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

GATEWAY=$(docker network inspect kind -f '{{range .IPAM.Config}}{{if eq .Subnet "172.23.0.0/16"}}{{.Gateway}}{{end}}{{end}}' 2>/dev/null || true)
if [ -z "$GATEWAY" ]; then
  GATEWAY=$(docker network inspect kind -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1 || true)
fi
if [ -z "$GATEWAY" ]; then
  echo "Error: kind network not found. Is the cluster running?"
  echo "Run: kind create cluster --name laba13"
  exit 1
fi

echo "Kind gateway: $GATEWAY"

sed "s/__KIND_GATEWAY__/$GATEWAY/g" "$DIR/deployment.yaml" | kubectl apply -f -
kubectl apply -f "$DIR/hpa.yaml"

echo "Deployed. NATS_URL=nats://$GATEWAY:4222"
echo "Pods:"
kubectl get pods -l app=assignment-checker
