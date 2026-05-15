import type { MenuKey } from "./AdminLayout";
import logo from "../assets/logo.png";

type SidebarProps = {
  selectedMenu: MenuKey;
  onSelectMenu: (menu: MenuKey) => void;
};

const menuItems: { key: MenuKey; label: string }[] = [
  { key: "dashboard", label: "대시보드" },
  { key: "upload", label: "이미지 업로드 및 결과 조회" },
  { key: "userManagement", label: "사용자 관리" },
  { key: "systemStatus", label: "시스템 상태" },
  { key: "settings", label: "설정" },
];

export default function Sidebar({ selectedMenu, onSelectMenu }: SidebarProps) {
  return (
    <aside style={styles.sidebar}>
      <div style={styles.logoBox}>
        <img src={logo} alt="logo" style={styles.logoIcon} />
        <div>
          <h2 style={styles.logoTitle}>Smart Glass</h2>
          <p style={styles.logoSubTitle}>관리자 페이지</p>
        </div>
      </div>

      <nav style={styles.menuList}>
        {menuItems.map((item) => {
          const isActive = selectedMenu === item.key;

          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onSelectMenu(item.key)}
              style={{
                ...styles.menuButton,
                ...(isActive ? styles.activeMenuButton : {}),
              }}
            >
              {item.label}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    width: "260px",
    minHeight: "100vh",
    padding: "24px 18px",
    backgroundColor: "#111827",
    color: "#FFFFFF",
    boxSizing: "border-box",
  },
  logoBox: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    marginBottom: "32px",
  },
  logoIcon: {
    width: "44px",
    height: "44px",
    borderRadius: "14px",
    objectFit: "cover",
  },
  logoTitle: {
    margin: 0,
    fontSize: "18px",
    fontWeight: 800,
  },
  logoSubTitle: {
    margin: "4px 0 0",
    fontSize: "13px",
    color: "#CBD5E1",
  },
  menuList: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  menuButton: {
    width: "100%",
    padding: "12px 14px",
    border: "none",
    borderRadius: "12px",
    backgroundColor: "transparent",
    color: "#CBD5E1",
    textAlign: "left",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
  },
  activeMenuButton: {
    backgroundColor: "#818489",
    color: "#FFFFFF",
  },
};