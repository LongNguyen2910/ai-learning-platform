# Fundamental Data Structures

## 1. Array vs. Linked List
An Array is a collection of elements stored at contiguous memory locations. It provides $O(1)$ random access time complexity via indexing, but insertion and deletion at arbitrary positions require shifting elements, yielding $O(n)$ time complexity.

A Linked List consists of nodes where each node contains a data field and a reference (pointer) to the next node. Unlike arrays, linked list elements are not stored contiguously in memory. Accessing an element takes $O(n)$ time because it requires traversing from the head. However, inserting or deleting a node takes $O(1)$ time once the position pointer is known.

## 2. Hash Tables
A Hash Table implements an associative array abstract data type that maps keys to values using a hash function. In the average case, search, insert, and delete operations take $O(1)$ time. In the worst case (when multiple keys collide and hash to the same bucket without adequate resizing), operations can degrade to $O(n)$. Collisions are commonly resolved using Chaining (linked lists in each bucket) or Open Addressing (probing).

## 3. Binary Search Tree (BST)
A Binary Search Tree is a node-based binary tree data structure where each node has at most two children. For any node, all keys in its left subtree are strictly less than its key, and all keys in its right subtree are strictly greater. In a balanced BST (such as an AVL tree or Red-Black tree), search, insertion, and deletion operations take $O(\log n)$ time. In an unbalanced degenerate tree (resembling a linked list), operations degrade to $O(n)$.
