import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { ApiError, apiRequest, onAuthExpired, type Session } from "./core/api";
import { LoginPage } from "./features/auth/login";
import { PeopleMemoryPage, PersonMemoryPage } from "./features/memory/people_page";
import { SelfMemoryPage } from "./features/memory/self_page";
import { OverviewPage } from "./features/overview/page";
import { PersonalityPage } from "./features/personality/page";
import { SettingsPage } from "./features/settings/page";
import { PanelShell } from "./layout/shell";
import { PageError, PageLoading } from "./shared/page_state";

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [startupError, setStartupError] = useState("");
  const [loginNotice, setLoginNotice] = useState("");

  useEffect(() => {
    const unsubscribe = onAuthExpired(() => setSession(null));
    apiRequest<Session>("/session")
      .then(setSession)
      .catch((caught: unknown) => {
        if (!(caught instanceof ApiError) || caught.status !== 401) {
          setStartupError(caught instanceof Error ? caught.message : String(caught));
        }
      })
      .finally(() => setChecking(false));
    return unsubscribe;
  }, []);

  if (checking) return <PageLoading label="正在确认 ai-love 登录状态" />;
  if (startupError) return <PageError message={startupError} />;
  if (session === null) {
    return (
      <LoginPage
        notice={loginNotice}
        onLogin={(value) => {
          setLoginNotice("");
          setSession(value);
        }}
      />
    );
  }

  function signedOut(message = "") {
    setLoginNotice(message);
    setSession(null);
  }

  return (
    <Routes>
      <Route element={<PanelShell session={session} onLogout={() => signedOut()} />}>
        <Route index element={<OverviewPage />} />
        <Route path="personality" element={<PersonalityPage />} />
        <Route path="memory/self" element={<SelfMemoryPage />} />
        <Route path="memory/people" element={<PeopleMemoryPage />} />
        <Route path="memory/people/:personId" element={<PersonMemoryPage />} />
        <Route path="settings" element={<SettingsPage onCredentialsChanged={signedOut} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
