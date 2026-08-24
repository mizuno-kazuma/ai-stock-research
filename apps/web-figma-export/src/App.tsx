import { BrowserRouter, Routes, Route } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import RecommendationsPage from "./pages/RecommendationsPage";
import StockDetailPage from "./pages/StockDetailPage";
import ScreenerPage from "./pages/ScreenerPage";
import FilingsHubPage from "./pages/FilingsHubPage";
import FxMacroPage from "./pages/FxMacroPage";
import ModelLabPage from "./pages/ModelLabPage";
import AgentConsolePage from "./pages/AgentConsolePage";
import PortfolioPage from "./pages/PortfolioPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/recommendations" element={<RecommendationsPage />} />
        <Route path="/stocks/:market/:ticker" element={<StockDetailPage />} />
        <Route path="/screener" element={<ScreenerPage />} />
        <Route path="/filings" element={<FilingsHubPage />} />
        <Route path="/macro" element={<FxMacroPage />} />
        <Route path="/model-lab" element={<ModelLabPage />} />
        <Route path="/agent" element={<AgentConsolePage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </BrowserRouter>
  );
}
