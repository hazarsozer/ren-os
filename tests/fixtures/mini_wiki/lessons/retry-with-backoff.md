---
title: "Lesson: retry flaky third-party API calls with exponential backoff"
type: lesson
---

# Lesson: retry flaky third-party API calls with exponential backoff

A flaky third-party payment API kept failing intermittently under load, and
naive immediate retries just hammered it harder and made things worse. The
fix was exponential backoff: each retry waits longer than the last, with
jitter added so many clients don't retry in lockstep. After adding backoff,
the same third-party API's error rate as seen by our callers dropped sharply
even though the provider's own reliability hadn't changed at all.
