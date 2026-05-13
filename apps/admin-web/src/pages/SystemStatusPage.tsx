const systems = [
  { name: "API 서버", status: "정상", detail: "요청 처리 가능" },
  { name: "추론 서버", status: "정상", detail: "GPU worker 대기 중" },
  { name: "Redis Queue", status: "대기", detail: "pending task 2개" },
  { name: "Object Storage", status: "정상", detail: "이미지 업로드 가능" },
];

export default function SystemStatusPage() {
  return (
    <section style={styles.grid}>
      {systems.map((system) => (
        <div key={system.name} style={styles.panel}>
          <p style={styles.cardTitle}>{system.name}</p>
          <strong style={styles.statusText}>{system.status}</strong>
          <p style={styles.description}>{system.detail}</p>
        </div>
      ))}
    </section>
  );
}

const styles: Record<string, React.CSSProperties> = {
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: "16px",
  },
  panel: {
    backgroundColor: "#FFFFFF",
    padding: "20px",
    borderRadius: "16px",
    boxShadow: "0 8px 24px rgba(15, 23, 42, 0.06)",
  },
  cardTitle: {
    margin: 0,
    color: "#64748B",
    fontSize: "14px",
  },
  statusText: {
    display: "block",
    margin: "10px 0",
    fontSize: "24px",
    color: "#16A34A",
  },
  description: {
    margin: 0,
    fontSize: "15px",
    color: "#64748B",
  },
};