// Deal Desk decision policy, written in Cedar (https://www.cedarpolicy.com - AWS open source).
//
// These are the rules that decide what the creator is allowed to do with an offer. They live here,
// as data, instead of being buried in Python, so the creator can read them, argue with them and
// change them without touching the code.
//
// TWO THINGS TO KNOW BEFORE YOU EDIT THIS FILE:
//
//  1. In Cedar, `forbid` always beats `permit`, and anything not permitted is denied. So the safe
//     way to tighten a rule is to add a `forbid`; you cannot accidentally widen access by adding one.
//  2. CreatorOS treats this file as a TIGHTENING layer only. The hard guard in pipeline.decide()
//     still runs, and a decision needs BOTH to allow it. Deleting a forbid here does not unlock
//     anything the built-in guard refuses. Adding one does take effect immediately.
//
// Entities:
//   principal  Creator::"<name>"
//   action     Action::"accept" | Action::"counter" | Action::"decline"
//   resource   Offer::"<id>" with attributes:
//                risk     "LOW" | "MEDIUM" | "HIGH" | "DO_NOT_ENGAGE"
//                override true when the creator explicitly overrode a risky verdict
//                checked  true once the Deal Desk has actually run its check
//                category the brand's category, or "" when it could not be determined

// -- accepting -----------------------------------------------------------------------------------

// An offer the desk rated LOW or MEDIUM can be accepted normally.
@id("accept_when_risk_is_acceptable")
permit (principal, action == Action::"accept", resource)
when { resource.risk == "LOW" || resource.risk == "MEDIUM" };

// A risky offer can still be accepted, but only through an explicit override, which is ledgered.
@id("accept_risky_only_with_override")
permit (principal, action == Action::"accept", resource)
when { resource.override == true };

// Nothing may be accepted before it has been checked. There is no evidence to accept on.
@id("never_accept_an_unchecked_offer")
forbid (principal, action == Action::"accept", resource)
unless { resource.checked == true };

// Belt and braces: spell out the refusal instead of relying on the absence of a permit.
@id("forbid_risky_accept_without_override")
forbid (principal, action == Action::"accept", resource)
when {
  (resource.risk == "HIGH" || resource.risk == "DO_NOT_ENGAGE") && resource.override == false
};

// -- countering and declining --------------------------------------------------------------------

// Countering or declining is always the creator's to make, at any risk level. Neither sends anything.
@id("counter_or_decline_is_always_allowed")
permit (principal, action in [Action::"counter", Action::"decline"], resource);

// -- your own rules go below here ------------------------------------------------------------------
//
// Examples you can uncomment. Each one only ever REMOVES a possibility:
//
// Never accept anything the desk did not rate LOW, no matter how much you want the deal:
//   @id("my_rule_only_low_risk")
//   forbid (principal, action == Action::"accept", resource)
//   unless { resource.risk == "LOW" };
//
// Never accept a gambling or crypto brand, even with an override:
//   @id("my_rule_no_gambling_or_crypto")
//   forbid (principal, action == Action::"accept", resource)
//   when { resource.category == "gambling" || resource.category == "crypto" };
