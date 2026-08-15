#!/bin/bash
# 雪花 ID + ORM 重构上线流程（在 core 节点执行）
set -e
NS=ailove

echo "[1/5] 缩容 DB 写入服务"
kubectl scale deploy -n $NS gateway director ai-agent memory ops-panel --replicas=0
for app in gateway director ai-agent memory ops-panel; do
    kubectl wait --for=delete pod -n $NS -l app=$app --timeout=120s 2>/dev/null || true
done

echo "[2/5] 执行数据库雪花迁移"
kubectl apply -f /tmp/db-migrate-job.yaml
kubectl wait --for=condition=complete job/ailove-dbmigrate -n $NS --timeout=900s
kubectl logs job/ailove-dbmigrate -n $NS | tail -5

echo "[3/5] 清空记忆 KV 桶"
kubectl apply -f /tmp/kv-flush-job.yaml
kubectl wait --for=condition=complete job/ailove-kvflush -n $NS --timeout=300s
kubectl logs job/ailove-kvflush -n $NS | tail -5

echo "[4/5] 恢复写入服务（新镜像）"
kubectl scale deploy -n $NS gateway director ai-agent memory ops-panel --replicas=1

echo "[5/5] 滚动重启边缘与核心服务"
kubectl rollout restart deploy -n $NS gptsovits avatar stream mcp extension-host

echo "DONE: 检查 gateway/ai-agent 日志确认恢复"
