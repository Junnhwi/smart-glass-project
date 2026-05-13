export default function SettingsPage() {
  return (
    <section style={styles.panel}>
      <h3 style={styles.sectionTitle}>설정</h3>

      <label style={styles.label}>API 서버 주소</label>
      <input style={styles.input} defaultValue="http://localhost:3000" />

      <label style={styles.label}>추론 서버 주소</label>
      <input style={styles.input} defaultValue="http://localhost:8000" />

      <label style={styles.label}>관리자 모드</label>
      <select style={styles.input} defaultValue="development">
        <option value="development">개발</option>
        <option value="production">운영</option>
      </select>

      <button style={styles.primaryButton}>설정 저장</button>
    </section>
  );
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    backgroundColor: "#FFFFFF",
    padding: "20px",
    borderRadius: "16px",
    boxShadow: "0 8px 24px rgba(15, 23, 42, 0.06)",
    maxWidth: "520px",
  },
  sectionTitle: {
    margin: "0 0 16px",
    fontSize: "18px",
  },
  label: {
    display: "block",
    margin: "14px 0 6px",
    color: "#475569",
    fontSize: "14px",
    fontWeight: 700,
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    padding: "12px 14px",
    borderRadius: "12px",
    border: "1px solid #CBD5E1",
    fontSize: "14px",
  },
  primaryButton: {
    marginTop: "18px",
    width: "100%",
    padding: "12px 14px",
    border: "none",
    borderRadius: "12px",
    backgroundColor: "#2563EB",
    color: "#FFFFFF",
    fontWeight: 800,
    cursor: "pointer",
  },
};