#!/bin/bash

echo "=========================================="
echo "   Irrigation Scheduler Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python installation..."
python3 --version

if [ $? -ne 0 ]; then
    echo "❌ Python 3 not found. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python found"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo "✅ Dependencies installed"
echo ""

# Run simulation
echo "=========================================="
echo "   Running Simulation"
echo "=========================================="
echo ""
python irrigation_scheduler.py

echo ""
echo "=========================================="
echo "   Setup Complete!"
echo "=========================================="
echo ""
echo "Generated files:"
echo "  📊 irrigation_dashboard.png"
echo "  📅 irrigation_schedule.csv"
echo "  🌐 irrigation_dashboard.html (open in browser)"
echo ""
echo "Next steps:"
echo "  1. View the dashboard: open irrigation_dashboard.png"
echo "  2. Check the schedule: cat irrigation_schedule.csv"
echo "  3. Try interactive version: open irrigation_dashboard.html"
echo ""
