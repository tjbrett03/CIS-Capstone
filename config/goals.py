# Defines the content goals selectable on the index page.
# Each key is the goal ID used in URL params and session storage.
# - label: display name shown in the UI
# - tone: sent to Claude as {goal_tone} to guide voice and style
# - length: sent to Claude as {goal_length} as a target word count
# - priority: sent to Ollama as {goal_priority} to guide interview focus, and to Claude as {goal_priority}
GOALS = {
    "event_promo": {
        "label": "Promote an Event",
        "tone": "Energetic, action-oriented",
        "length": "100–150 words",
        "priority": "Drive registrations with clear reason to attend, date/location, and specific compelling detail",
    },
    "program_promo": {
        "label": "Promote a Program or Service",
        "tone": "Informative, inviting, accessible",
        "length": "150–200 words",
        "priority": "Build awareness; answer what it is, who it serves, and access method without jargon",
    },
    "program_story": {
        "label": "Tell a Program Story",
        "tone": "Warm, human, specific",
        "length": "200–300 words",
        "priority": "Create emotional connection through one real person's experience following five-element arc",
    },
    "funder_report": {
        "label": "Report Impact to a Funder",
        "tone": "Evidence-forward, credible, mission-aligned",
        "length": "300–400 words",
        "priority": "Open with human story, support with data, close connecting outcomes to funder priorities",
    },
    "donor_appeal": {
        "label": "Appeal to a Donor",
        "tone": "Motivating, values-driven, personal",
        "length": "150–250 words",
        "priority": "Lead with specific moment, connect to reader values, close with one clear donation ask",
    },
    "volunteer_recruit": {
        "label": "Recruit a Volunteer",
        "tone": "Energetic, purpose-driven, personal",
        "length": "150–250 words",
        "priority": "Lead with specific moment, connect to reader's desire to contribute, close with one clear volunteer ask",
    },
}