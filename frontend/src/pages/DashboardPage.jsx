import React, { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";

import { KpiCard } from "../components/KpiCard";
import { Legend } from "../components/Legend";

const runtimeHost = typeof window !== "undefined" ? window.location.hostname : "localhost";
const runtimeProtocol = typeof window !== "undefined" ? window.location.protocol : "http:";
const runtimePort = typeof window !== "undefined" ? window.location.port : "";
const defaultGatewayPort = runtimePort === "31034" ? "31033" : "8580";
const gatewayUrl = import.meta.env.VITE_API_GATEWAY_URL || `${runtimeProtocol}//${runtimeHost}:${defaultGatewayPort}`;

const fallbackCenter = [55.7558, 37.6173];

async function fetchOverview(parameter, region) {
  const response = await fetch(`${gatewayUrl}/dashboard/overview?parameter=${parameter}&region=${region}`);
  if (!response.ok) {
    throw new Error(`Overview request failed: ${response.status}`);
  }
  return response.json();
}

async function fetchMap(parameter, region) {
  const response = await fetch(`${gatewayUrl}/dashboard/map?parameter=${parameter}&region=${region}`);
  if (!response.ok) {
    throw new Error(`Map request failed: ${response.status}`);
  }
  return response.json();
}

function riskColor(value, limit) {
  if (limit <= 0) {
    return "#4fbf8f";
  }
  const ratio = value / limit;
  if (ratio < 0.7) {
    return "#4fbf8f";
  }
  if (ratio < 1) {
    return "#f0b14a";
  }
  if (ratio < 1.5) {
    return "#ef6d4f";
  }
  return "#bf3f5b";
}

export function DashboardPage() {
  const [parameter, setParameter] = useState("pm25");
  const [region, setRegion] = useState("Moscow");
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [overview, setOverview] = useState(null);
  const [mapData, setMapData] = useState({ points: { items: [] }, heatmap: { items: [] } });

  const load = async () => {
    try {
      setStatus("loading");
      const [overviewData, mapPayload] = await Promise.all([fetchOverview(parameter, region), fetchMap(parameter, region)]);
      setOverview(overviewData);
      setMapData(mapPayload);
      setStatus("ready");
      setError(null);
    } catch (err) {
      setStatus("error");
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
  }, [parameter, region]);

  const kpi = overview?.analysis?.kpi || {};
  const report = overview?.report || {};
  const points = mapData?.points?.items || [];
  const cells = mapData?.heatmap?.items || [];
  const exceedances = overview?.analysis?.exceedances?.items || [];

  const mapCenter = useMemo(() => {
    if (!points.length) {
      return fallbackCenter;
    }
    const latest = points[0];
    return [latest.latitude, latest.longitude];
  }, [points]);

  const mapeValue = Number(kpi.forecast_mape || 0);
  const mapeTarget = Number(kpi.forecast_mape_target || 15);
  const refreshTarget = Number(kpi.data_refresh_target_minutes || 5);

  return (
    <div className="app">
      <div className="grain" />
      <header className="hero">
        <div>
          <p className="eyebrow">EcoWatch Public Monitoring</p>
          <h1>Environmental overview</h1>
          <p className="hero-sub">Citizen sensors + stationary posts + open data feeds with threshold alerts and map layers.</p>
          <div className="hero-tags">
            <span>Update every &lt; 5 min</span>
            <span>Forecast target MAPE &lt; 15%</span>
            <span>Capacity plan 100 000 sensors</span>
          </div>
        </div>

        <div className="control-panel">
          <label>
            Parameter
            <select value={parameter} onChange={(event) => setParameter(event.target.value)}>
              <option value="pm25">PM2.5</option>
              <option value="pm10">PM10</option>
              <option value="co2">CO2</option>
              <option value="no2">NO2</option>
              <option value="ph">pH</option>
              <option value="turbidity">Turbidity</option>
              <option value="dissolved_oxygen">Dissolved oxygen</option>
              <option value="noise_db">Noise</option>
              <option value="radiation">Radiation</option>
              <option value="temperature_c">Temperature</option>
              <option value="humidity_pct">Humidity</option>
            </select>
          </label>
          <label>
            Region
            <input value={region} onChange={(event) => setRegion(event.target.value)} />
          </label>
          <div className="actions">
            <button onClick={load}>Refresh</button>
            <span className={`status status-${status}`}>{status}</span>
          </div>
        </div>
      </header>

      {error ? <div className="error">{error}</div> : null}

      <section className="kpi-grid">
        <KpiCard
          title="Refresh Target"
          value={`< ${refreshTarget} min`}
          target="Near real-time telemetry"
          ok={refreshTarget <= 5}
        />
        <KpiCard
          title="Forecast MAPE"
          value={`${mapeValue.toFixed(2)}%`}
          target={`Target < ${mapeTarget}%`}
          ok={mapeValue <= mapeTarget}
        />
        <KpiCard
          title="Daily Measurements"
          value={String(report.measurements || 0)}
          target="Daily summary"
          ok={(report.measurements || 0) > 0}
        />
        <KpiCard
          title="Active Alerts"
          value={String(report.alerts || 0)}
          target="Alerting in place"
          ok={true}
        />
      </section>

      <section className="content-grid">
        <article className="panel panel-map">
          <div className="panel-head">
            <h2>Eco Map Layer</h2>
            <p>{points.length} points, {cells.length} heat cells</p>
          </div>
          <Legend />
          <MapContainer center={mapCenter} zoom={11} scrollWheelZoom className="map-view">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {points.map((point) => (
              <CircleMarker
                key={point.reading_id}
                center={[point.latitude, point.longitude]}
                radius={6}
                pathOptions={{ color: "#2d9380", fillColor: "#2d9380", fillOpacity: 0.6 }}
              >
                <Popup>
                  <strong>{point.parameter}</strong>
                  <br />
                  {point.value} {point.unit}
                  <br />
                  {point.sensor_id}
                </Popup>
              </CircleMarker>
            ))}

            {cells.map((cell) => {
              const limit = Number(overview?.analysis?.kpi?.forecast_mape_target || 15);
              const color = riskColor(cell.average_value, limit);
              return (
                <CircleMarker
                  key={cell.cell_id}
                  center={[cell.center.latitude, cell.center.longitude]}
                  radius={Math.max(10, Math.min(30, cell.average_value / 2))}
                  pathOptions={{ color, fillColor: color, fillOpacity: 0.18 }}
                >
                  <Popup>
                    <strong>Heat cell</strong>
                    <br />
                    Avg: {Number(cell.average_value).toFixed(2)}
                    <br />
                    Max: {Number(cell.max_value).toFixed(2)}
                    <br />
                    Count: {cell.count}
                  </Popup>
                </CircleMarker>
              );
            })}
          </MapContainer>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Exceedances</h2>
            <p>{exceedances.length} latest</p>
          </div>
          <div className="stack">
            {exceedances.length ? (
              exceedances.map((item) => (
                <div className="stack-item" key={item.alert_id}>
                  <div>
                    <strong>{item.parameter}</strong>
                    <p>{item.region}</p>
                  </div>
                  <div>
                    <strong>{item.value} {item.unit}</strong>
                    <p className={`sev sev-${item.severity}`}>{item.severity}</p>
                  </div>
                </div>
              ))
            ) : (
              <p className="muted">No exceedances yet for this filter.</p>
            )}
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Daily Summary</h2>
            <p>{report.date || "today"}</p>
          </div>
          <div className="summary-grid">
            {Object.entries(report.summary || {}).map(([key, value]) => (
              <div key={key} className="summary-item">
                <h3>{key}</h3>
                <p>avg {Number(value.avg).toFixed(2)}</p>
                <p>max {Number(value.max).toFixed(2)}</p>
                <p>count {Math.round(Number(value.count || 0))}</p>
              </div>
            ))}
            {!Object.keys(report.summary || {}).length ? <p className="muted">No report rows yet.</p> : null}
          </div>
        </article>
      </section>
    </div>
  );
}
