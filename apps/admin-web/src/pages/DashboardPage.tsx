import SummaryCard from "../shared/ui/SummaryCard";
import InferenceTable from "../shared/ui/InferenceTable";
import { mockResults } from "../shared/mock/mockData";

export default function DashboardPage() {
  const completedCount = mockResults.filter((item) => item.status === "completed").length;
  const pendingCount = mockResults.filter((item) => item.status === "pending").length;
  const failedCount = mockResults.filter((item) => item.status === "failed").length;

  return (
    <>
      <section style={styles.cardGrid}>
        <SummaryCard title="전체 작업" value={mockResults.length} />
        <SummaryCard title="완료" value={completedCount} />
        <SummaryCard title="대기" value={pendingCount} />
        <SummaryCard title="실패" value={failedCount} />
      </section>

      <section style={styles.panel}>
        <h3 style={styles.sectionTitle}>최근 추론 작업 목록</h3>
        <InferenceTable results={mockResults} />
      </section>
    </>
  );
}

const styles: Record<string, React.CSSProperties> = {
  cardGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: "16px",
    marginBottom: "24px",
  },
  panel: {
    backgroundColor: "#FFFFFF",
    padding: "20px",
    borderRadius: "16px",
    boxShadow: "0 8px 24px rgba(15, 23, 42, 0.06)",
    overflowX: "auto",
  },
  sectionTitle: {
    margin: "0 0 16px",
    fontSize: "18px",
  },
};