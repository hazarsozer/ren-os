---
title: "Decision: Postgres over MongoDB for widget-tracker"
type: decision
---

# Decision: Postgres over MongoDB for widget-tracker

We chose Postgres instead of MongoDB for the widget-tracker project's storage
layer. Order history requires multi-table joins across customers, orders, and
line items, and Postgres's relational joins handle that far more cleanly than
MongoDB's document model would. MongoDB was considered first because the team
already had experience with it, but the join-heavy order-history queries were
the deciding factor.
