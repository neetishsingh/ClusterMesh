import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { OverviewPage } from "@/pages/Overview";
import { NodesPage } from "@/pages/Nodes";
import { JobsPage } from "@/pages/Jobs";
import { JobDetailPage } from "@/pages/JobDetail";
import { LogsPage } from "@/pages/Logs";
import { LibrariesPage } from "@/pages/Libraries";
import { ClusterPage } from "@/pages/Cluster";
import { MeshPage } from "@/pages/Mesh";
import { MemoryPage } from "@/pages/Memory";
import { NotebookPage } from "@/pages/Notebook";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="nodes" element={<NodesPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="jobs/:jobId" element={<JobDetailPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="libraries" element={<LibrariesPage />} />
          <Route path="cluster" element={<ClusterPage />} />
          <Route path="mesh" element={<MeshPage />} />
          <Route path="memory" element={<MemoryPage />} />
          <Route path="notebook" element={<NotebookPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
