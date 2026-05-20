import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 20,
  duration: "30s",
};

export default function () {
  const health = http.get("http://localhost:8580/health");
  check(health, { "gateway health": (response) => response.status === 200 });

  const dashboard = http.get("http://localhost:8580/dashboard/overview?parameter=pm25&region=Moscow");
  check(dashboard, { "dashboard ok": (response) => response.status === 200 });
  sleep(1);
}
