import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ListingDetail } from "./pages/ListingDetail";
import { Listings } from "./pages/Listings";
import { Stats } from "./pages/Stats";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Listings />} />
        <Route path="listings/:autoId" element={<ListingDetail />} />
        <Route path="stats" element={<Stats />} />
      </Route>
    </Routes>
  );
}
