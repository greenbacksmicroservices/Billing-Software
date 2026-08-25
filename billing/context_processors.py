from billing.utils import INDIAN_STATES_AND_UTS

def global_gst_states(request):
    """
    Exposes the central list of Indian states and UTs with 2-digit GST state codes
    to all templates globally across Admin, Company, and Accountant panels.
    """
    return {
        'indian_states': INDIAN_STATES_AND_UTS,
    }
