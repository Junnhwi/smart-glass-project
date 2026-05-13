type SummaryCardProps = {
  title: string;
  value: number;
};

export default function SummaryCard({ title, value }: SummaryCardProps) {
  return (
    <div style={styles.card}>
      <p style={styles.title}>{title}</p>
      <strong style={styles.value}>{value}</strong>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: "#FFFFFF",
    padding: "20px",
    borderRadius: "16px",
    boxShadow: "0 8px 24px rgba(15, 23, 42, 0.06)",
  },
  title: {
    margin: 0,
    color: "#64748B",
    fontSize: "14px",
  },
  value: {
    display: "block",
    marginTop: "8px",
    fontSize: "28px",
  },
};