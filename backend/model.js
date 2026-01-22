// backend/model.js

const SOILS = {
  sandy:  { FC: 0.15, PWP: 0.07 },
  loam:   { FC: 0.27, PWP: 0.12 },
  clay:   { FC: 0.33, PWP: 0.18 }
};

const CROPS = {
  wheat: {
    rootDepth: 0.6,
    p: 0.45,
    kcInitial: 0.4,
    kcMid: 1.15,
    kcLate: 0.3,
    daysInitial: 20,
    daysMid: 60,
    daysLate: 30
  },
  maize: {
    rootDepth: 1.0,
    p: 0.5,
    kcInitial: 0.3,
    kcMid: 1.2,
    kcLate: 0.35,
    daysInitial: 25,
    daysMid: 55,
    daysLate: 30
  }
};

function buildKcSeries(cropName, nDays) {
  const crop = CROPS[cropName];
  if (!crop) throw new Error(`Unknown crop: ${cropName}`);

  const { kcInitial, kcMid, kcLate, daysInitial, daysMid, daysLate } = crop;
  const kc = [];

  for (let d = 0; d < nDays; d++) {
    if (d < daysInitial) kc.push(kcInitial);
    else if (d < daysInitial + daysMid) kc.push(kcMid);
    else kc.push(kcLate);
  }

  return kc;
}

function computeSoilProps(soilType, cropName) {
  const soil = SOILS[soilType];
  const crop = CROPS[cropName];
  if (!soil) throw new Error(`Unknown soil type: ${soilType}`);
  if (!crop) throw new Error(`Unknown crop: ${cropName}`);

  const { FC, PWP } = soil;
  const { rootDepth, p } = crop;

  const maxStorage = (FC - PWP) * rootDepth * 1000;
  const RAW = p * maxStorage;
  const stressThreshold = maxStorage - RAW;

  return {
    maxStorage,
    RAW,
    stressThreshold,
    FC,
    PWP,
    rootDepth
  };
}

function buildDefaultWeather(nDays) {
  const weather = [];
  for (let d = 0; d < nDays; d++) {
    weather.push({ rain: 0, et0: 4 });
  }
  return weather;
}

function simulateAndSchedule(params) {
  const {
    nDays,
    soilType,
    cropType,
    area,
    weather = buildDefaultWeather(params.nDays),
    initialFraction = 1.0
  } = params;

  if (!Number.isFinite(nDays) || nDays <= 0) {
    throw new Error("nDays must be > 0");
  }

  const kcSeries = buildKcSeries(cropType, nDays);
  const { maxStorage, stressThreshold } =
    computeSoilProps(soilType, cropType);

  let S = initialFraction * maxStorage;

  const days = [], soilWater = [], irrigation = [],
        rain = [], etcSeries = [], stressFlag = [];

  for (let t = 0; t < nDays; t++) {
    const dayIndex = t + 1;
    const w = weather[t] || { rain: 0, et0: 4 };
    const kc = kcSeries[t] || kcSeries[kcSeries.length - 1];
    const etc = kc * w.et0;

    let I = 0;
    if (S <= stressThreshold) {
      I = maxStorage - S;
      const maxPerEvent = 40;
      if (I > maxPerEvent) I = maxPerEvent;
    }

    S = S + w.rain + I - etc;
    if (S > maxStorage) S = maxStorage;
    if (S < 0) S = 0;

    const isStress = S < stressThreshold;

    days.push(dayIndex);
    soilWater.push(S);
    irrigation.push(I);
    rain.push(w.rain);
    etcSeries.push(etc);
    stressFlag.push(isStress);
  }

  const totalIrrigationMm = irrigation.reduce((sum, x) => sum + x, 0);
  const totalIrrigationM3 = (totalIrrigationMm / 1000) * area;
  const totalIrrigationLiters = totalIrrigationM3 * 1000;
  const stressDays = stressFlag.filter(Boolean).length;

  return {
    days,
    soilWater,
    irrigation,
    rain,
    etc: etcSeries,
    stressFlag,
    stats: {
      maxStorage,
      stressThreshold,
      totalIrrigationMm,
      totalIrrigationLiters,
      stressDays
    }
  };
}

module.exports = {
  simulateAndSchedule,
  buildDefaultWeather,
  computeSoilProps,
  SOILS,
  CROPS
};
