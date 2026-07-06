---
title: "Lesson: distributed timestamp comparisons break under clock skew"
type: lesson
---

# Lesson: distributed timestamp comparisons break under clock skew

Two servers compared event timestamps directly to decide ordering, and it
worked fine in testing but broke in production because of clock skew between
machines whose clocks had drifted apart. A few milliseconds of clock skew was
enough to flip the ordering of events that were actually seconds apart in
real wall-clock time. The lesson: never trust raw timestamp comparisons across
machines for ordering; use a logical clock or a single authoritative clock
source instead.
