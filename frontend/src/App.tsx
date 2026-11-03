import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useStore } from "./lib/store";
import Auth from "./pages/Auth";
import Projects from "./pages/Projects";
import Dashboard from "./pages/Dashboard";
import UploadPage from "./pages/Upload";
import Cleaning from "./pages/Cleaning";
import Hypotheses from "./pages/Hypotheses";
import { Advanced, Correlation, Descriptive, EDA, Factor, Inferential, Reliability, Survey } from "./pages/Analyses";
import { Export, Interpretation, Reports } from "./pages/Output";

export default function App() {
  const { user } = useStore();
  return (
    <HashRouter>
      {!user ? (
        <Routes><Route path="*" element={<Auth />} /></Routes>
      ) : (
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/eda" element={<EDA />} />
            <Route path="/cleaning" element={<Cleaning />} />
            <Route path="/survey" element={<Survey />} />
            <Route path="/descriptive" element={<Descriptive />} />
            <Route path="/inferential" element={<Inferential />} />
            <Route path="/reliability" element={<Reliability />} />
            <Route path="/hypotheses" element={<Hypotheses />} />
            <Route path="/correlation" element={<Correlation />} />
            <Route path="/factor" element={<Factor />} />
            <Route path="/advanced" element={<Advanced />} />
            <Route path="/interpretation" element={<Interpretation />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/export" element={<Export />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </Layout>
      )}
    </HashRouter>
  );
}
