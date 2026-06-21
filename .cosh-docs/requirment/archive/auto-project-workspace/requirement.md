# Auto Project Workspace

## Background

The current project creation flow treats Project Execution as enabled when the user enters a workspace path. If the workspace field is empty, the project is created as a normal project and does not get Project Execution behavior.

The clarified requirement is to make executable projects the default. When a user creates a project without entering a workspace path, the system should automatically create a random project workspace and bind the new project to it. This removes the need for users to understand or prepare a filesystem path before they can use Project Execution.

## Target User

- A Virtual Office user creating a new project.
- The user expects the project to be ready for agent execution after creation.
- The user may not know what workspace path to enter, or may not care where the project workspace lives as long as it is visible afterwards.

## Product Goal

Make newly created projects executable by default. If the user does not provide a workspace path, the system creates a formal project workspace automatically, binds the project to it, enables Project Execution, and clearly shows the resulting workspace path and status.

## Confirmed Product Decisions

- Default project type is executable Project Execution project.
- If the workspace path is omitted for an executable project, the system automatically creates a workspace.
- The automatically created workspace is the project's formal workspace, not a temporary scratch space.
- The workspace is used for task execution, artifact display, and file changes.
- Users can still create a normal non-Project Execution project.
- The normal project option is presented through an explicit project-type switch in the creation form.
- The project-type switch defaults to executable project.
- After an automatic workspace is created, the UI must clearly show the workspace path and workspace status.
- If automatic workspace creation fails, project creation fails and the user sees the failure reason.
- When deleting a project with an automatically created workspace, the user should be asked whether to also delete that workspace.
- Automatically created workspace names should communicate project ownership and include the project name plus timestamp, such as `project-title-20260616143536`.

## In Scope

1. Update project creation so executable project is the default type.
2. Add or expose a clear project-type switch during project creation: executable project versus normal project.
3. Keep executable project selected by default.
4. If executable project is selected and the user leaves workspace path empty, create an automatic workspace.
5. Bind the created workspace to `workspacePath`.
6. Set `projectExecutionEnabled` to true for the created executable project.
7. Store the workspace kind and validation status as part of the project.
8. Show the generated workspace path and status after creation.
9. Preserve manual workspace path behavior when the user explicitly enters a path.
10. Preserve normal project creation when the user switches to normal project.
11. Fail project creation if automatic workspace creation fails.
12. Ask whether to delete the automatically created workspace when deleting the owning project.
13. Name automatic workspaces using project name plus timestamp.
14. Ensure artifact listing continues to work because the project now has a valid workspace by default.

## Out of Scope

- Migrating existing normal projects to executable projects.
- Automatically renaming the workspace when the project title changes after creation.
- Supporting multiple workspaces per project.
- Workspace backup, archive, export, or cloud sync.
- Changing Project Execution task execution, review, rework, or acceptance semantics.
- Changing artifact management beyond relying on the default workspace.
- General-purpose filesystem management outside project-owned workspaces.
- Automatically deleting workspaces without user confirmation.

## Product Constraints

- The user must be able to intentionally create a normal project.
- Automatic workspace creation must be visible enough that the user understands where agent work and artifacts will live.
- Automatic workspace creation failure must not silently downgrade to a normal project.
- The automatic workspace is formal project data and should be treated with the same caution as user-provided workspaces.
- Project deletion must not silently remove an automatic workspace without asking the user.

## Success Criteria

The feature succeeds when:

1. A user can create a project without entering a workspace path and gets an executable Project Execution project.
2. The created project has a valid workspace path, workspace kind, workspace status, and `projectExecutionEnabled: true`.
3. The created workspace is named with project title plus timestamp.
4. The user can see the generated workspace path and status after creation.
5. A user can still create a normal project by switching project type.
6. A user-provided workspace path still works as before for executable projects.
7. If automatic workspace creation fails, the project is not created and the user sees a clear error.
8. Deleting a project with an automatic workspace asks whether the workspace should also be deleted.
