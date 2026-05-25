import { useState } from "react";

type UploadLog = {
  time: string;
  result: string;
};

type UploadResponse = {
  upload_status?: string;
  message?: string;
  [key: string]: unknown;
};

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState("대기 중");
  const [preview, setPreview] = useState<string | null>(null);
  const [logs, setLogs] = useState<UploadLog[]>([]);
  const [resultJson, setResultJson] = useState<UploadResponse | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];

    if (!selected) return;

    setFile(selected);
    setPreview(URL.createObjectURL(selected));
    setStatus("파일 선택 완료");
    setResultJson(null);
  };

  const uploadImage = async () => {
    if (!file) {
      setStatus("파일을 선택하세요 ❗");
      return;
    }

    const formData = new FormData();
    formData.append("image", file); // 백엔드 FileInterceptor('image')와 반드시 일치
    formData.append("timestamp", new Date().toISOString());
    formData.append("device_id", "admin_test");

    setStatus("업로드 중... ⏳");

    try {
      const API_BASE_URL =
        import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8002";

      if (!file) {
        setStatus("이미지 파일이 없습니다 ❌");
        return;
      }

      setStatus("업로드 허용 요청 중...");

      // 1. 업로드 허용 요청
      const authRes = await fetch(`${API_BASE_URL}/media/upload-authorizations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          filename: file.name,
          contentType: file.type,
          size: file.size,
        }),
      });

      const authData = await authRes.json();

      if (!authRes.ok) {
        console.error("업로드 허용 실패:", authData);
        setStatus("업로드 허용 실패 ❌");
        return;
      }

      const { uploadUrl, imageKey } = authData;

      setStatus("Object Storage 업로드 중...");

      // 2. presigned URL로 Object Storage 직접 업로드
      const uploadRes = await fetch(uploadUrl, {
        method: "PUT",
        headers: {
          "Content-Type": file.type,
        },
        body: file,
      });

      if (!uploadRes.ok) {
        setStatus("Object Storage 업로드 실패 ❌");
        return;
      }

      setStatus("캡처 등록 중...");

      // 3. 캡처 등록
      const captureRes = await fetch(`${API_BASE_URL}/media/captures`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          imageKey,
          userId: "demo-user",
          memoryId: "demo-memory",
          capturedAt: new Date().toISOString(),
        }),
      });

      const captureData = await captureRes.json();
      setResultJson(captureData);

      if (!captureRes.ok) {
        console.error("캡처 등록 실패:", captureData);
        setStatus("캡처 등록 실패 ❌");
        return;
      }

      setStatus("캡처 등록 성공 ✅");
      setLogs((prev) => [
        { time: new Date().toLocaleTimeString(), result: "성공" },
        ...prev,
      ]);
    } catch (err) {
      console.error("업로드 오류:", err);
      setStatus("업로드 오류 ❌");
      setLogs((prev) => [
        { time: new Date().toLocaleTimeString(), result: "서버 오류" },
        ...prev,
      ]);
    }
  };

  return (
    <div style={styles.twoColumn}>
      <section style={styles.panel}>
        <h3 style={styles.sectionTitle}>이미지 업로드</h3>

        <label style={styles.label}>이미지 선택</label>
        <input
          style={styles.input}
          type="file"
          accept="image/*"
          onChange={handleFileChange}
        />

        <button style={styles.primaryButton} onClick={uploadImage}>
          업로드 및 추론 실행
        </button>

        <div style={styles.statusBox}>
          <strong>업로드 상태</strong>
          <p style={styles.statusText}>{status}</p>
        </div>

        <div style={styles.logBox}>
          <strong>최근 업로드 로그</strong>
          <ul style={styles.logList}>
            {logs.map((log, idx) => (
              <li key={idx}>
                [{log.time}] {log.result}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section style={styles.panel}>
        <h3 style={styles.sectionTitle}>추론 결과</h3>

        <div style={styles.previewBox}>
          {preview ? (
            <img src={preview} alt="preview" style={styles.previewImage} />
          ) : (
            <span>업로드한 이미지가 표시됩니다.</span>
          )}
        </div>

        <pre style={styles.jsonBox}>
          {resultJson
            ? JSON.stringify(resultJson, null, 2)
            : "업로드 후 결과가 표시됩니다."}
        </pre>
      </section>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  twoColumn: {
    display: "grid",
    gridTemplateColumns: "380px 1fr",
    gap: "20px",
    alignItems: "start",
  },
  panel: {
    backgroundColor: "#FFFFFF",
    padding: "20px",
    borderRadius: "16px",
    boxShadow: "0 8px 24px rgba(15, 23, 42, 0.06)",
  },
  sectionTitle: {
    margin: "0 0 16px",
    fontSize: "18px",
    fontWeight: 700,
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
  statusBox: {
    marginTop: "20px",
    padding: "14px",
    borderRadius: "12px",
    backgroundColor: "#F8FAFC",
  },
  statusText: {
    margin: "8px 0 0",
    color: "#334155",
  },
  logBox: {
    marginTop: "18px",
    padding: "14px",
    borderRadius: "12px",
    backgroundColor: "#F8FAFC",
  },
  logList: {
    margin: "10px 0 0",
    paddingLeft: "18px",
    color: "#475569",
    fontSize: "14px",
  },
  previewBox: {
    height: "260px",
    borderRadius: "16px",
    border: "1px dashed #CBD5E1",
    backgroundColor: "#F8FAFC",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    marginBottom: "16px",
    color: "#64748B",
  },
  previewImage: {
    width: "100%",
    height: "100%",
    objectFit: "cover",
  },
  jsonBox: {
    margin: 0,
    padding: "16px",
    borderRadius: "12px",
    backgroundColor: "#111827",
    color: "#E5E7EB",
    fontSize: "13px",
    overflowX: "auto",
    minHeight: "180px",
  },
};