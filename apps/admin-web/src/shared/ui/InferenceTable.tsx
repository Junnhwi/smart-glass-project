import type { InferenceItem, InferenceStatus } from "../../entities/inference/types";

type InferenceTableProps = {
  results: InferenceItem[];
};

const statusLabel: Record<InferenceStatus, string> = {
  completed: "완료",
  pending: "대기",
  failed: "실패",
};

export default function InferenceTable({ results }: InferenceTableProps) {
  return (
    <table style={styles.table}>
      <thead>
        <tr>
          <th style={styles.th}>이미지 ID</th>
          <th style={styles.th}>사용자 ID</th>
          <th style={styles.th}>상태</th>
          <th style={styles.th}>감지 객체</th>
          <th style={styles.th}>위치</th>
          <th style={styles.th}>신뢰도</th>
          <th style={styles.th}>촬영 시간</th>
          <th style={styles.th}>처리 시간</th>
        </tr>
      </thead>

      <tbody>
        {results.map((item) => (
          <tr key={item.imageId}>
            <td style={styles.td}>{item.imageId}</td>
            <td style={styles.td}>{item.userId}</td>
            <td style={styles.td}>
              <span style={getBadgeStyle(item.status)}>
                {statusLabel[item.status]}
              </span>
            </td>
            <td style={styles.td}>{item.result?.objects.join(", ") ?? "-"}</td>
            <td style={styles.td}>{item.result?.location ?? "-"}</td>
            <td style={styles.td}>
              {item.result ? `${Math.round(item.result.confidence * 100)}%` : "-"}
            </td>
            <td style={styles.td}>{item.capturedAt}</td>
            <td style={styles.td}>{item.processedAt ?? "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function getBadgeStyle(status: InferenceStatus): React.CSSProperties {
  const base: React.CSSProperties = {
    display: "inline-block",
    padding: "4px 10px",
    borderRadius: "999px",
    fontSize: "13px",
    fontWeight: 700,
  };

  if (status === "completed") {
    return { ...base, backgroundColor: "#DCFCE7", color: "#166534" };
  }

  if (status === "pending") {
    return { ...base, backgroundColor: "#FEF9C3", color: "#854D0E" };
  }

  return { ...base, backgroundColor: "#FEE2E2", color: "#991B1B" };
}

const styles: Record<string, React.CSSProperties> = {
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "14px",
  },
  th: {
    padding: "12px",
    textAlign: "left",
    borderBottom: "1px solid #E2E8F0",
    color: "#475569",
    whiteSpace: "nowrap",
  },
  td: {
    padding: "12px",
    borderBottom: "1px solid #F1F5F9",
    whiteSpace: "nowrap",
  },
};