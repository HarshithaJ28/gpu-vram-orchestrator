import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const latency = new Trend('request_latency');
const successRate = new Rate('success_rate');
const throughput = new Counter('throughput');

// Spike test configuration - sudden traffic increase
export const options = {
  stages: [
    // Start with 10 users
    { duration: '1m', target: 10 },
    // Spike to 100 users (10x traffic)
    { duration: '30s', target: 100 },
    // Stay at 100 for 2 minutes
    { duration: '2m', target: 100 },
    // Sudden drop to 5 users
    { duration: '30s', target: 5 },
    // Ramp back up to 50 users
    { duration: '1m', target: 50 },
    // Return to normal
    { duration: '30s', target: 10 },
    // Cool down
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    'http_req_duration': ['p(95)<1000'],  // P95 latency < 1s during spike
    'http_req_failed': ['rate<0.05'],      // Error rate < 5% (higher tolerance for spike)
    'success_rate': ['rate>0.95'],         // Success rate > 95%
  },
};

const API_URL = __ENV.API_URL || 'http://localhost:8000';

const models = [
  'fraud-detection-v1',
  'sentiment-analysis-v2',
  'recommendation-engine-v1',
];

function getRandomModel() {
  return models[Math.floor(Math.random() * models.length)];
}

function generateInputData() {
  return {
    features: [
      Math.random(),
      Math.random(),
      Math.random(),
      Math.random(),
      Math.random(),
    ],
  };
}

export default function () {
  // Continuous prediction load
  group('Spike Test - Predictions', function () {
    const model = getRandomModel();
    const inputData = generateInputData();

    const response = http.post(
      `${API_URL}/predict`,
      JSON.stringify({
        model_id: model,
        input_data: inputData,
        return_timing: true,
      }),
      {
        headers: {
          'Content-Type': 'application/json',
        },
        timeout: '10s',
      }
    );

    latency.add(response.timings.duration);
    throughput.add(1);

    const success = check(response, {
      'status is 200': (r) => r.status === 200,
      'has predictions': (r) => r.json('predictions') !== null,
      'response time < 1000ms': (r) => r.timings.duration < 1000,
      'no errors': (r) => r.status !== 500 && r.status !== 503,
    });

    successRate.add(success);
    errorRate.add(!success);

    // Very short sleep to maximize concurrent load
    sleep(0.01);
  });

  // Check system health during spike
  if (__ITER % 100 === 0) {
    group('System Health Check', function () {
      const response = http.get(`${API_URL}/status`, {
        headers: {
          'Accept': 'application/json',
        },
      });

      check(response, {
        'system responding': (r) => r.status === 200,
      });

      sleep(0.1);
    });
  }
}
