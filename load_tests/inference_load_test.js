import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const latency = new Trend('request_latency');
const successRate = new Rate('success_rate');
const throughput = new Counter('throughput');
const cacheHitRate = new Gauge('cache_hit_rate');

// Test configuration
export const options = {
  stages: [
    // Ramp up from 0 to 50 virtual users over 2 minutes
    { duration: '2m', target: 50 },
    // Stay at 50 virtual users for 5 minutes
    { duration: '5m', target: 50 },
    // Ramp up to 100 virtual users over 2 minutes
    { duration: '2m', target: 100 },
    // Stay at 100 virtual users for 5 minutes
    { duration: '5m', target: 100 },
    // Ramp down to 0 virtual users over 2 minutes
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    'http_req_duration': ['p(95)<500'],  // 95% of requests < 500ms
    'http_req_failed': ['rate<0.1'],      // Error rate < 10%
    'success_rate': ['rate>0.9'],         // Success rate > 90%
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
    customer_id: `cust_${Math.floor(Math.random() * 100000)}`,
  };
}

export default function () {
  // Test 1: Simple prediction
  group('Predictions', function () {
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
      }
    );

    latency.add(response.timings.duration);
    throughput.add(1);

    const success = check(response, {
      'status is 200': (r) => r.status === 200,
      'has predictions': (r) => r.json('predictions') !== null,
      'has gpu_id': (r) => r.json('gpu_id') !== null,
      'latency < 500ms': (r) => r.timings.duration < 500,
    });

    successRate.add(success);
    errorRate.add(!success);

    sleep(0.1);
  });

  // Test 2: Check status
  group('Status', function () {
    const response = http.get(`${API_URL}/status`, {
      headers: {
        'Accept': 'application/json',
      },
    });

    check(response, {
      'status is 200': (r) => r.status === 200,
      'has cache info': (r) => r.json('cache') !== null,
      'has gpu info': (r) => r.json('gpus') !== null,
    });

    // Extract cache hit rate
    if (response.status === 200) {
      const chit = response.json('cache.hit_rate');
      if (chit !== null && chit !== undefined) {
        cacheHitRate.add(chit);
      }
    }

    sleep(0.5);
  });

  // Test 3: List models (every 10 iterations)
  if (__VU % 10 === 0) {
    group('List Models', function () {
      const response = http.get(`${API_URL}/models`, {
        headers: {
          'Accept': 'application/json',
        },
      });

      check(response, {
        'status is 200': (r) => r.status === 200,
        'has models': (r) => r.json('models') !== null && r.json('models').length > 0,
      });

      sleep(1);
    });
  }

  // Test 4: Get metrics (every 20 iterations)
  if (__VU % 20 === 0) {
    group('Metrics', function () {
      const response = http.get(`${API_URL}/metrics`, {
        headers: {
          'Accept': 'application/json',
        },
      });

      check(response, {
        'status is 200': (r) => r.status === 200,
      });

      sleep(2);
    });
  }
}

export function handleSummary(data) {
  return {
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
    'summary.json': JSON.stringify(data),
  };
}
