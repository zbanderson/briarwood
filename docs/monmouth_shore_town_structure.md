# Monmouth Shore Town Structure

## Purpose

This document defines Briarwood's first explicit Monmouth County shore-town structure for:

- Avon by the Sea
- Spring Lake
- Belmar
- Bradley Beach
- Sea Girt
- Manasquan

The goal is not to pretend every field is perfectly sourced today. The goal is to make the model structure explicit so these towns can be analyzed consistently, with confidence reduced when hard market inputs are missing.

## Model Layers

### 1. County Macro Sentiment

Monmouth County now includes a county-level macro sentiment layer sourced from FRED-style county series.

Current inputs:

- unemployment rate
- per-capita personal income growth
- county house price index growth
- median days-on-market year-over-year change

These inputs are normalized into a `county_macro_sentiment` score on a `0.0-1.0` scale.

### 2. Town Coastal Profile

The six Monmouth shore towns now have an explicit Briarwood profile layer that captures persistent coastal demand and land-constrained desirability.

Current structured profile fields:

- `coastal_profile_signal`
- `scarcity_signal`

These are currently Briarwood-managed structured inputs, not claimed as official market datasets.

## Key Rule

County macro sentiment is source-backed.
Town coastal profile is structured Briarwood judgment.

They should not be treated as the same type of evidence.

## Towns Covered

- Avon by the Sea
- Spring Lake
- Belmar
- Bradley Beach
- Sea Girt
- Manasquan

## Current Limitations

- hard town-level price/population/liquidity/flood coverage is still strongest for Belmar in the local fixture set
- school signal is still not fully sourced in the live path
- the coastal profile helps structure sentiment, but it does not replace hard town-level market data

## Intended Outcome

These towns should screen as high-sentiment coastal submarkets when:

- county macro conditions are supportive
- local demand/liquidity remains healthy
- coastal scarcity remains a real driver

But the system should still lower confidence whenever town-level evidence is incomplete.
