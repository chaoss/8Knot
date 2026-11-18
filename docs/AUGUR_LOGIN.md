# **8Knot+Augur User Sessions**

## **Intro**

---

With this feature, users can:

1. Create an account on an Augur database frontend page.
2. Organize repos and orgs into named groups in Augur, specific to their user account.
3. Log in to to Augur via 8Knot and see aggregate visualizations of their named groups.
4. See the groups created by the Augur user who registered the 8Knot application with the Augur frontend.

## **Roles**

---

There are three personas required for this integration:

1. The application owner (Admin).
2. The application deployer (Dep).
3. The application user (User).

The job of the application owner (Admin) is to:

1. Log into the Augur front-end with credentials intended for Admin-level access
2. Create repo groups in their profile for the consumption of other users logging into the Augur frontend via the same 8Knot instance
3. Provide the 'client_secret' and 'application_id' values to the Dep role

In turn, the job of the application deployer (Dep) is to:

1. Receive the 'client_secret' and 'application_id' credentials from the Admin
2. Use those credentials to link 8Knot instance to Augur frontend as described below

Finally, the job of the application user (User) is to:

1. Access the deployed application
2. Click the 'Log In' button which will redirect to the Augur front end
3. Create their own groups of repos
4. Navigate back to the 8Knot app they were using and refresh the app

## **Setup 8Knot to enable Login and user and admin groups**

---

1. Clone [github.com/chaoss/8Knot/dev] (Dep)
   - We use a docker compose multi-container application build strategy.
   - Ports 8050 (*Dash*) and 6379 (*Redis*) are assumed to be available. If this isn't possible, modifications to the docker-compose.yml file may be necessary.
   - Inter-pod name resolution is done with Docker network's DNS.

2. Create an application in Augur front-end (Admin)
   - Navigate to Augur instance's front-end by URL.
   - Create an Admin-level Augur account.
   - Create an application for Admin account to get an *app_id* and a *client_secret* to register your 8Knot instance with Augur. You can use the url [http://0.0.0.0:8050/] if you're developing locally.

3. Prepare client environment (Dep)
   - App will communicate w/ Augur front-end via HTTP and w/ its database Augur instance via direct connection.
     - The following environment variables will need to be available to the application at startup in an '.env' file at the same directory-level at 'app.py':
       - AUGUR_DATABASE=
       - AUGUR_HOST=
       - AUGUR_PASSWORD=
       - AUGUR_PORT=
       - AUGUR_SCHEMA=
       - AUGUR_USERNAME=
       - AUGUR_APP_ID=
         - You'll need to use the *app_id* from the Augur front-end here.
       - AUGUR_CLIENT_SECRET=
         - You'll need to use the *client_secret* from the Augur front-end here.
       - AUGUR_SESSION_GENERATE_ENDPOINT=<!!!>/api/unstable/user/session/generate
       - AUGUR_USER_GROUPS_ENDPOINT=\<!!!\>/api/unstable/user/groups/repos?columns=repo_id,repo_git
       - AUGUR_USER_ACCOUNT_ENDPOINT=\<!!!\>/account/settings
       - AUGUR_USER_AUTH_ENDPOINT=\<!!!\>/user/authorize?client_id=<AUGUR_APP_ID>&response_type=code
         - You'll need to use the *app_id* from the Augur front-end here to fill in the "<AUGUR_APP_ID>".
       - AUGUR_ADMIN_NAME_ENDPOINT=\<!!!\>/api/unstable/application/
       - AUGUR_ADMIN_GROUP_NAMES_ENDPOINT=\<!!!\>/api/unstable/application/groups/name
       - AUGUR_ADMIN_GROUPS_ENDPOINT=\<!!!\>/api/unstable/application/group/repos
       - AUGUR_LOGIN_ENABLED=True

    - Any place that there is a \<!!!\> should be replaced by your Augur instance's URL. For example, if your application is running on port 5038 on localhost, \<!!!\> will be replaced by 0.0.0.0:5038
    - The first six environment variables are used to connect to database, not for front-end. Instructions to get these credentials are in the project README.md file.

## **8Knot at Runtime**

---

- Assuming that you have 8Knot booted and available.

- Log into Augur with 'Login' button in the top right of the page.

- You should be directed to the Augur front-end that you specified in the '.env' file, be able to create or log into your profile, and be redirected back to the index (home) page of 8Knot.

- When you've been redirected, your Augur username should be filled-in where the 'Login' button was originally.

- If there's a problem logging in, you should still see the login button but a popover should tell you that login has failed. Detailed logs of failure are available.

- Augur front-end defined groups are available in the searchbar pre-fixed with your username. For example if your username is "rockiesFan" and you name a group "searchGroup", the name will be "rockiesFan_searchGroup" in 8Knot.
