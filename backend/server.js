// backend/server.js

const express = require('express');
const cors = require('cors');
const { simulateAndSchedule } = require('./model');

const app = express();
app.use(cors());
app.use(express.json());

app.get('/', (req, res) => {
  res.send({ status: 'ok', message: 'Crop Water Stress Scheduler API' });
});

app.post('/simulate', (req, res) => {
  try {
    const {
      nDays,
      soilType,
      cropType,
      area,
      weather,
      initialFraction
    } = req.body;

    const result = simulateAndSchedule({
      nDays: Number(nDays) || 30,
      soilType: soilType || 'loam',
      cropType: cropType || 'wheat',
      area: Number(area) || 1000,
      weather,
      initialFraction: initialFraction ?? 1.0
    });

    res.json({ ok: true, result });
  } catch (err) {
    console.error(err);
    res.status(400).json({ ok: false, error: err.message });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Backend server running on http://localhost:${PORT}`);
});
