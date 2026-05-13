import { useState } from "react";
import Sidebar from "./Sidebar";
import DashboardPage from "../pages/DashboardPage";
import UploadPage from "../pages/UploadPage";
import UserManagementPage from "../pages/UserManagementPage";
import SystemStatusPage from "../pages/SystemStatusPage";
import SettingsPage from "../pages/SettingsPage";

export type MenuKey =
  | "dashboard"
  | "upload"
  | "errorLog"
  | "userManagement"
  | "systemStatus"
  | "settings";

const pageInfo: Record<MenuKey, { title: string; description: string }> = {
  dashboard: {
    title: "대시보드",
    description: "전체 작업 현황을 확인합니다.",
  },
  upload: {
    title: "이미지 업로드 및 결과 조회",
    description: "이미지를 업로드하고 추론 결과를 확인합니다.",
  },
  errorLog: {
    title: "실패 로그",
    description: "실패한 작업과 에러 메시지를 확인합니다.",
  },
  userManagement: {
    title: "사용자 관리",
    description: "사용자별 데이터와 연결 디바이스를 확인합니다.",
  },
  systemStatus: {
    title: "시스템 상태",
    description: "서버, 큐, 추론 서비스 상태를 확인합니다.",
  },
  settings: {
    title: "설정",
    description: "관리자 화면 및 API 설정을 관리합니다.",
  },
};

export default function AdminLayout() {
  const [selectedMenu, setSelectedMenu] = useState<MenuKey>("dashboard");

  return (
    <div style={styles.layout}>
      <Sidebar selectedMenu={selectedMenu} onSelectMenu={setSelectedMenu} />

      <main style={styles.main}>
        <header style={styles.header}>
          <p style={styles.subTitle}>Smart Glass Admin</p>
          <h1 style={styles.title}>{pageInfo[selectedMenu].title}</h1>
          <p style={styles.description}>{pageInfo[selectedMenu].description}</p>
        </header>

        {selectedMenu === "dashboard" && <DashboardPage />}
        {selectedMenu === "upload" && <UploadPage />}
        {selectedMenu === "userManagement" && <UserManagementPage />}
        {selectedMenu === "systemStatus" && <SystemStatusPage />}
        {selectedMenu === "settings" && <SettingsPage />}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  layout: {
    display: "flex",
    minHeight: "100vh",
    backgroundColor: "#F8FAFC",
    color: "#111827",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  main: {
    flex: 1,
    padding: "32px",
    boxSizing: "border-box",
    overflowX: "auto",
  },
  header: {
    marginBottom: "24px",
  },
  subTitle: {
    margin: 0,
    fontSize: "14px",
    color: "#64748B",
  },
  title: {
    margin: "6px 0",
    fontSize: "30px",
    fontWeight: 800,
  },
  description: {
    margin: 0,
    fontSize: "15px",
    color: "#64748B",
  },
};