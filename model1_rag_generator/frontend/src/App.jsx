import { Link, Route, Routes } from "react-router-dom";
import Compare from "./pages/Compare.jsx";
import CreateRun from "./pages/CreateRun.jsx";
import Experiments from "./pages/Experiments.jsx";
import Home from "./pages/Home.jsx";
import Results from "./pages/Results.jsx";
import RunDetail from "./pages/RunDetail.jsx";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-4 py-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <Link to="/" className="font-bold text-indigo-400">
          SVAGA 3.0
        </Link>
        <Link to="/create" className="hover:text-white">
          New run
        </Link>
        <Link to="/results" className="hover:text-white">
          Results
        </Link>
        <Link to="/compare" className="hover:text-white">
          Compare
        </Link>
        <Link to="/experiments" className="hover:text-white">
          Experiments
        </Link>
        <a href="/api/docs" className="ml-auto text-slate-500 hover:text-slate-300">
          API docs
        </a>
      </header>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/create" element={<CreateRun />} />
        <Route path="/runs/:runId" element={<RunDetail />} />
        <Route path="/experiments" element={<Experiments />} />
        <Route path="/results" element={<Results />} />
        <Route path="/compare" element={<Compare />} />
      </Routes>
    </div>
  );
}
