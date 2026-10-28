# Manual review: task_dependencies



test_new_task_is_todo .................................... OK  
test_task_without_dependencies_can_complete .............. OK  
test_blocked_until_dependency_is_done .................... Unclear (fixed by clarifying the prompt)  
test_chain_must_complete_in_order ........................ Unclear (fixed by clarifying the prompt)  
test_all_dependencies_are_required ....................... Unclear (fixed by clarifying the prompt)  
test_unknown_dependency_is_422 ........................... OK  
test_self_dependency_is_422 .............................. OK  
test_two_task_cycle_is_409 ............................... OK  
test_longer_cycle_is_409 ................................. OK  
test_completing_twice_is_409 ............................. OK  
test_no_new_dependencies_on_a_done_task .................. OK  
test_adding_a_valid_dependency_and_unknown_task .......... OK  
test_status_cannot_be_supplied ........................... OK  
test_added_dependencies_block_completion ................. OK (added in review)  
test_diamond_dependencies_are_not_cycles ................. OK (added in review)  
test_adding_a_dependency_to_an_unknown_task_is_404 ....... OK (added in review)  
test_unknown_and_self_dependencies_change_nothing ........ OK (added in review)  
test_response_fields_match_the_interface ................. OK (added in review)  
test_empty_or_missing_title_and_bad_depends_on_are_422 ... OK (added in review)  
test_add_dependency_body_is_validated .................... OK (added in review)  

Changes made after review:

- Unclear: the prompt says a task can be completed only when every dependency is done, but never says which status code an unmet dependency returns. Three checks and the sec_complete_ignores_deps security bug expect 409. The interface offers 409 (cycle_or_wrong_status, conflict) but 422 or 400 are equally plausible, so the public prompt now says '(otherwise 409)', in the same style as '(otherwise 422)' for unknown dependencies.
- Added: a dependency added after creation (POST /tasks/{id}/dependencies) blocks completion until it is done, not only dependencies given at creation.
- Added: a diamond (b and c depend on a, d depends on b and c) is accepted, and closing it back onto a is a 409 cycle.
- Added: adding a dependency to an unknown task id is 404 (unknown subject) as opposed to 422 for an unknown dependency.
- Added: rejected unknown and self dependencies leave the dependency list unchanged.
- Added: declared response fields on create, read, add-dependency and complete.
- Added: an empty or missing title, a depends_on that is not a list, and a dependency body without task_id or with an extra field are 422.

Remaining lower-priority coverage:

- Unclear, not tested: adding a dependency to a done task when the dependency is itself done. The prompt states the rule without exception (409) but explains it with 'unfinished work'; the checks only use a todo dependency.
- Not stated, not tested: adding the same dependency twice, duplicate ids inside depends_on, and which error wins when a request is wrong in two ways (for example a done task and an unknown dependency).
- There is no list route, so a create rejected for an unknown dependency cannot be shown to leave no task behind.

Validation: reference 20/20, stub 0/20, deterministic, 12 automatic bugs caught (all 12 sampled were killed) + security bugs 3/3.

s 
