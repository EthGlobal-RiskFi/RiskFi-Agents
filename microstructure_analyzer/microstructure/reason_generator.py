from __future__ import annotations
from typing import Dict, List, Any

def generate_microstructure_reasons(
    depth_up: Dict[str, float],
    depth_down: Dict[str, float],
    slippage_curve: List[Dict[str, float]],
    cliffs: List[Dict[str, float]],
    active_liq_ratio: float,
    lp_concentration: Dict[str, float],
    cross_spread_bps: float,
    mev_exposure: Dict[str, Any],
    score: int
) -> List[str]:
    """Generate intelligent, contextual reasons based on microstructure analysis.
    
    Returns a prioritized list of key findings and recommendations.
    """
    reasons = []
    
    # Categorize the overall health
    if score >= 80:
        health_status = "excellent"
    elif score >= 60:
        health_status = "good"
    elif score >= 40:
        health_status = "moderate"
    else:
        health_status = "poor"
    
    # 1. Overall market quality assessment
    reasons.append(f"Market microstructure health is {health_status} (score: {score}/100).")
    
    # 2. Depth analysis - identify key issues
    depth_issues = []
    
    # Check 5% depth
    depth_5_up = depth_up.get("pct5", 0)
    depth_5_down = depth_down.get("pct5", 0)
    
    if depth_5_up < 100_000:
        depth_issues.append(f"Very thin depth for 5% upward moves (${depth_5_up:,.0f})")
    elif depth_5_up < 250_000:
        depth_issues.append(f"Limited depth for 5% upward moves (${depth_5_up:,.0f})")
    
    if depth_5_down < 100_000:
        depth_issues.append(f"Very thin depth for 5% downward moves (${depth_5_down:,.0f})")
    elif depth_5_down < 250_000:
        depth_issues.append(f"Limited depth for 5% downward moves (${depth_5_down:,.0f})")
    
    # Check 10% depth
    depth_10_up = depth_up.get("pct10", 0)
    depth_10_down = depth_down.get("pct10", 0)
    
    if depth_10_up < 500_000:
        depth_issues.append(f"Insufficient depth for 10% upward moves (${depth_10_up:,.0f})")
    
    if depth_10_down < 500_000:
        depth_issues.append(f"Insufficient depth for 10% downward moves (${depth_10_down:,.0f})")
    
    # Add depth reason
    if depth_issues:
        reasons.append("Depth concerns: " + "; ".join(depth_issues[:2]) + ".")
    else:
        avg_depth_5 = (depth_5_up + depth_5_down) / 2
        if avg_depth_5 > 1_000_000:
            reasons.append(f"Strong market depth with ${avg_depth_5:,.0f} average for 5% moves.")
        else:
            reasons.append(f"Adequate market depth with ${avg_depth_5:,.0f} average for 5% moves.")
    
    # 3. Liquidity cliff analysis
    if cliffs:
        max_cliff = max([c['deltaLRatio'] for c in cliffs], default=0)
        nearby_cliffs = [c for c in cliffs if abs(c['tick'] - cliffs[0].get('tick', 0)) <= 100]
        
        if max_cliff > 0.5:
            if nearby_cliffs:
                reasons.append(f"Critical liquidity cliff detected near current price (ratio: {max_cliff:.2f}) - expect volatile price action.")
            else:
                reasons.append(f"Significant liquidity cliffs present (max ratio: {max_cliff:.2f}) - potential for price jumps.")
        elif max_cliff > 0.2:
            reasons.append(f"Moderate liquidity variations detected (max ratio: {max_cliff:.2f}).")
    
    # 4. Slippage analysis
    if slippage_curve:
        # Analyze slippage for common trade sizes
        slippage_5k = next((s['slippagePct'] for s in slippage_curve if abs(s['notionalQuote'] - 5000) < 100), None)
        slippage_25k = next((s['slippagePct'] for s in slippage_curve if abs(s['notionalQuote'] - 25000) < 100), None)
        slippage_100k = next((s['slippagePct'] for s in slippage_curve if abs(s['notionalQuote'] - 100000) < 100), None)
        
        slippage_issues = []
        if slippage_5k and abs(slippage_5k) > 0.5:
            slippage_issues.append(f"$5k trades experience {abs(slippage_5k):.2f}% slippage")
        if slippage_25k and abs(slippage_25k) > 1.0:
            slippage_issues.append(f"$25k trades experience {abs(slippage_25k):.2f}% slippage")
        if slippage_100k and abs(slippage_100k) > 2.0:
            slippage_issues.append(f"$100k trades experience {abs(slippage_100k):.2f}% slippage")
        
        if slippage_issues:
            reasons.append("High slippage detected: " + "; ".join(slippage_issues[:2]) + ".")
        elif slippage_25k and abs(slippage_25k) < 0.5:
            reasons.append(f"Excellent price execution with minimal slippage ({abs(slippage_25k):.2f}% for $25k trades).")
    
    # 5. Active liquidity analysis
    if active_liq_ratio < 0.3:
        reasons.append(f"Poor liquidity concentration with only {active_liq_ratio:.1%} active near current price - expect high volatility.")
    elif active_liq_ratio < 0.5:
        reasons.append(f"Suboptimal liquidity distribution ({active_liq_ratio:.1%} active) may lead to price instability.")
    elif active_liq_ratio > 0.7:
        reasons.append(f"Well-concentrated liquidity ({active_liq_ratio:.1%} active) provides stable pricing.")
    
    # 6. LP concentration risk
    top1 = lp_concentration.get('top1Share', 0)
    top5 = lp_concentration.get('top5Share', 0)
    hhi = lp_concentration.get('hhi', 0)
    
    if top1 > 0.3:
        reasons.append(f"High concentration risk: largest LP controls {top1:.1%} of liquidity - vulnerable to single-actor manipulation.")
    elif top1 > 0.2:
        reasons.append(f"Moderate LP concentration with top provider at {top1:.1%} share.")
    
    if hhi > 0.2:
        reasons.append(f"Market concentration elevated (HHI: {hhi:.3f}) - limited LP diversity.")
    elif hhi < 0.1:
        reasons.append(f"Healthy LP diversity (HHI: {hhi:.3f}) reduces manipulation risk.")
    
    # 7. MEV exposure
    mev_score = mev_exposure.get('score', 0)
    mev_badge = mev_exposure.get('evidence', {}).get('sandwichDensity', 'unknown')
    
    if mev_score > 70 or mev_badge == "elevated":
        reasons.append("Elevated MEV exposure detected - consider using private mempools or MEV protection.")
    elif mev_score > 50:
        reasons.append("Moderate MEV risk - larger trades may attract sandwich attacks.")
    elif mev_score < 30:
        reasons.append("Low MEV exposure indicates robust market structure.")
    
    # 8. Cross-venue spread (if available)
    if cross_spread_bps > 0:
        if cross_spread_bps > 50:
            reasons.append(f"Wide cross-venue spread ({cross_spread_bps:.1f} bps) suggests arbitrage opportunities.")
        elif cross_spread_bps > 20:
            reasons.append(f"Moderate price discrepancy across venues ({cross_spread_bps:.1f} bps).")
        elif cross_spread_bps < 10:
            reasons.append(f"Tight cross-venue alignment ({cross_spread_bps:.1f} bps) indicates efficient markets.")
    
    # 9. Key recommendations based on score
    if score < 40:
        reasons.append("⚠️ Consider alternative venues or waiting for improved conditions before large trades.")
    elif score < 60:
        reasons.append("Consider breaking up large orders and using limit orders to minimize impact.")
    elif score >= 80:
        reasons.append("Market conditions favorable for efficient execution across all trade sizes.")
    
    # Return top 5-7 most relevant reasons
    return reasons[:7]

def generate_summary_insight(score: int, depth_up_5: float, active_liq_ratio: float, 
                            top1_share: float, mev_badge: str) -> str:
    """Generate a single-line executive summary of market conditions."""
    
    issues = []
    
    if depth_up_5 < 100_000:
        issues.append("thin orderbook")
    if active_liq_ratio < 0.4:
        issues.append("poor liquidity distribution")
    if top1_share > 0.25:
        issues.append("high LP concentration")
    if mev_badge == "elevated":
        issues.append("MEV vulnerability")
    
    if not issues:
        if score >= 80:
            return "Excellent market structure with deep liquidity and stable pricing dynamics."
        elif score >= 60:
            return "Good market conditions with adequate depth and reasonable execution quality."
        else:
            return "Moderate market structure with room for improvement in depth and stability."
    else:
        return f"Market shows {', '.join(issues[:2])} - exercise caution with large orders."