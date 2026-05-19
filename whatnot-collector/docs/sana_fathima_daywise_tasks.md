# Sana Fathima Day-Wise Task Plan

This plan is meant to give Sana a clear, practical path through the current product and operations work without needing to guess priorities.

## Focus Area

Sana should focus on the operator-facing workflow quality of the app:

- inventory editing speed
- customer data clarity
- Whatnot and TikTok sales workflow polish
- session tools usability
- QA for the dense ERP-style desktop experience

The goal is not to do abstract cleanup. The goal is to make daily operations faster and more reliable.

## Week 1 Plan

### Day 1: Inventory Editor QA And Cleanup

Goal:
- review the redesigned inventory product editor and identify any remaining duplication, wasted space, or broken field flow

Tasks:
- test the top product edit strip thoroughly:
  - product name
  - SKU auto-generation
  - barcode
  - cost
  - retail
  - gender
- verify the top strip is the only source of truth for those fields
- check that TikTok fields no longer conflict with core product fields
- test image URL save flow:
  - confirm link is saved
  - confirm remote image downloads and stores locally
- list any fields that still feel duplicated or misplaced

Deliverable:
- short QA note in markdown with:
  - bugs found
  - UX friction
  - suggested fixes

Files to review:
- `dashboard-vite/src/views/company/Inventory.jsx`
- `server/api.py`

### Day 2: Inventory Workflow Tightening

Goal:
- make the product editor faster for operators who edit many products in sequence

Tasks:
- improve keyboard-first behavior where helpful
- test previous/next product navigation in the editor
- verify sticky save area always stays usable
- check collapsible sections:
  - Notes
  - Assistant
  - Description
  - TikTok advanced attributes
  - TikTok compliance
- identify fields that should be collapsed by default vs immediately visible
- propose any label changes that reduce confusion

Deliverable:
- one implementation note with:
  - keep visible
  - collapse by default
  - move elsewhere

Primary outcome:
- faster product editing with less scrolling

### Day 3: Customer Section Platform Split Review

Goal:
- make customer data easier to understand by source

Tasks:
- review customer screens for:
  - Whatnot customers
  - TikTok Live customers
  - TikTok Shop customers
- verify linked identities display correctly
- check whether filters and labels clearly show platform source
- identify duplicate or confusing customer terminology
- test customer drawer/profile flow
- note any missing useful operator actions

Deliverable:
- customer UX review with:
  - what is working
  - what is unclear
  - what should be simplified

Files to review:
- `dashboard-vite/src/views/company/Customers.jsx`
- `dashboard-vite/src/views/company/CustomerProfileDrawer.jsx`

### Day 4: Whatnot And TikTok Session Workflow QA

Goal:
- verify that session-based workflows feel clean and predictable

Tasks:
- test Whatnot Auctions flow:
  - select session
  - upload labels PDF
  - preview updated PDF
  - confirm sales and cancelled orders behavior
- test TikTok Live Auctions flow:
  - select session
  - upload CSV
  - preview/import orders
  - upload labels PDF
  - download updated PDF
- verify cancelled vs confirmed visibility is easy to understand
- check lot search, customer grouping, and session filters
- log any workflow blockers or confusing steps

Deliverable:
- operations test report with concrete bugs and UX fixes

Files to review:
- `dashboard-vite/src/views/company/AuctionResults.jsx`
- `dashboard-vite/src/views/company/PickList.jsx`
- `dashboard-vite/src/views/company/TikTokLiveSetup.jsx`
- `dashboard-vite/src/views/company/TikTokLiveSessionDetail.jsx`

### Day 5: Polish Pass And Handoff

Goal:
- convert the week’s findings into a clean actionable handoff

Tasks:
- group issues into:
  - urgent bugs
  - operator UX issues
  - low-priority polish
- attach screenshots where useful
- suggest exact UI text changes where current wording is vague
- identify 3 to 5 highest-impact improvements for next week

Deliverable:
- one final handoff note with:
  - issues found
  - recommended fixes
  - priority order

## Working Rules For Sana

- do not redesign unrelated pages during this task block
- do not remove data fields without noting the impact
- prefer operator speed over visual decoration
- flag any case where the same business field appears in multiple places
- if a flow is confusing, describe the exact click path that caused confusion

## Suggested Daily Update Format

Sana can post updates in this format:

```md
## Day X Update

Done:
- ...

Found:
- ...

Blocked:
- ...

Next:
- ...
```

## Priority Summary

If time gets tight, this is the order to follow:

1. Inventory editor QA
2. Whatnot/TikTok session workflow QA
3. Customer platform split review
4. UX polish recommendations

