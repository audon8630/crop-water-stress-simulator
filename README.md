# Crop Water Stress Simulator

A field-scale soil moisture simulation and adaptive irrigation scheduling system that minimizes irrigation water use while keeping crop water stress below critical thresholds.

## Problem Statement
Agriculture consumes the majority of global freshwater resources. Fixed irrigation schedules often result in water wastage or crop stress. This project simulates soil moisture dynamics in the crop root zone and recommends optimal irrigation timing and volume using weather-driven evapotranspiration.

## Approach
- Root-zone soil moisture modeled using a bucket model
- Daily water balance:
  - Precipitation
  - Crop evapotranspiration (ET₀ × Kc)
  - Irrigation
  - Drainage beyond root zone
- Crop water stress controlled using a stress threshold based on readily available water (RAW)
- Adaptive irrigation scheduler minimizes water use while avoiding stress

## Features
- Field-scale soil moisture simulation
- Weather-driven evapotranspiration
- Crop water stress detection
- Automatic irrigation scheduling
- REST API backend (Node.js + Express)

## Tech Stack
- Backend: Node.js, Express
- Modeling: JavaScript
- Version Control: Git, GitHub
