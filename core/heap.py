"""Array-based binary min-heap, written by us (no heapq in the engine).

Reference: Cormen, Leiserson, Rivest, Stein, "Introduction to Algorithms" (CLRS), ch. 6
(heap property, sift-up/down). Children of index i are 2i+1 and 2i+2; parent is (i-1)//2.
push and pop are O(log n), peek is O(1).

Items are compared with `<`. The crisis queue stores tuples
(-score, deadline, created_at, ticket_id, version), so the smallest tuple is the most urgent.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations


class MinHeap:
    def __init__(self) -> None:
        self._a: list = []

    def __len__(self) -> int:
        return len(self._a)

    def push(self, item) -> None:
        self._a.append(item)
        self._sift_up(len(self._a) - 1)

    def peek(self):
        if not self._a:
            raise IndexError("peek from an empty heap")
        return self._a[0]

    def pop(self):
        if not self._a:
            raise IndexError("pop from an empty heap")
        top = self._a[0]
        last = self._a.pop()
        if self._a:
            self._a[0] = last
            self._sift_down(0)
        return top

    def items(self) -> list:
        """Copy of the stored items (heap order, not sorted)."""
        return list(self._a)

    def _sift_up(self, i: int) -> None:
        a = self._a
        while i > 0:
            parent = (i - 1) // 2
            if a[i] < a[parent]:
                a[i], a[parent] = a[parent], a[i]
                i = parent
            else:
                break

    def _sift_down(self, i: int) -> None:
        a, n = self._a, len(self._a)
        while True:
            left, right, smallest = 2 * i + 1, 2 * i + 2, i
            if left < n and a[left] < a[smallest]:
                smallest = left
            if right < n and a[right] < a[smallest]:
                smallest = right
            if smallest == i:
                return
            a[i], a[smallest] = a[smallest], a[i]
            i = smallest
