# Start with the official Python 3.11 slim base image
FROM python:3.11-slim

# Set environment variables for Python best practices
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- CRITICAL CONFIGURATION FOR DYNAMIC USERS ---

# 1. Define a generic home directory for any non-root user that will run the container.
ENV HOME=/home/nonroot

# 3. Create a group, create the home directory, and set permissions.
#    - Create a group named 'appgroup' with the GID.
#    - Create the home directory.
#    - Change ownership to root:appgroup. The user will be arbitrary, but the group is fixed.
#    - Set permissions so the owner (root) and any member of 'appgroup' can write to it.
#    - The 'setgid' bit (g+s) ensures new files/dirs created in HOME inherit the group ID.
RUN mkdir -p ${HOME} && \
    chmod 777 ${HOME} && \
    chmod g+s ${HOME}

# 4. Add the user's local bin directory (where pip installs executables) to the PATH.
#    This is essential for finding commands installed by `pip install --user`.
ENV PATH="${HOME}/.local/bin:${PATH}"

# 5. Set the working directory. Any command will now run from this writable directory.
WORKDIR ${HOME}

# NOTE: We DO NOT use the `USER` instruction. The container will start as root
# by default, but Kubernetes will immediately switch to the non-root user
# specified in the securityContext.

# A default command for standalone testing.
CMD ["python", "--version"]
