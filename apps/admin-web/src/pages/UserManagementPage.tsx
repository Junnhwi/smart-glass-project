const users = [
  {
    userId: "dummy_user",
    uploadCount: 0,
    lastUpload: "upload time",
    devices: ["dummy_glass"],
  },
];

export default function UserManagementPage() {
  return (
    <section style={styles.panel}>
      <h3 style={styles.sectionTitle}>사용자 목록</h3>

      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>사용자 ID</th>
            <th style={styles.th}>업로드 수</th>
            <th style={styles.th}>최근 업로드</th>
            <th style={styles.th}>연결 디바이스</th>
          </tr>
        </thead>

        <tbody>
          {users.map((user) => (
            <tr key={user.userId}>
              <td style={styles.td}>{user.userId}</td>
              <td style={styles.td}>{user.uploadCount}</td>
              <td style={styles.td}>{user.lastUpload}</td>
              <td style={styles.td}>{user.devices.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

const styles: Record<string, React.CSSProperties> = {
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
  },
  td: {
    padding: "12px",
    borderBottom: "1px solid #F1F5F9",
  },
};